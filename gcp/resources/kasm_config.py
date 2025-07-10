from pulumi import Config
from pulumi_kubernetes.batch.v1 import Job, JobSpecArgs
from pulumi_kubernetes.core.v1 import PodTemplateSpecArgs, PodSpecArgs, ContainerArgs, EnvVarArgs, EnvVarSourceArgs, SecretKeySelectorArgs, ConfigMap
import pulumi
import pulumi_gcp
import json



config = Config()
data = config.require_object("data")
gcp_config = Config("gcp")
secrets = config.require_secret_object("data")
additional_zone = data.get("additional_kasm_zone") or []


class KasmConfig:
    def __init__(self, gcp_cluster, kasm_helm, kasm_agent, get_kasm_config_script, get_kasm_config_configmap, gcp_network):

        # upstream_auth_address and proxy_hostname environmental variables for different zones
        env_vars = [
                       EnvVarArgs(
                           name=f"{zone['name']}_UPSTREAM_AUTH_ADDRESS",
                           value=zone["domain"]
                       ) for zone in additional_zone
                   ] + [
                       EnvVarArgs(
                           name=f"{zone['name']}_PROXY_HOSTNAME",
                           value=f'{zone["proxy_domain"]}'
                       ) for zone in additional_zone
                   ]

        # number of additional zones environmental variables
        env_vars.append(EnvVarArgs(
            name="ADDITIONAL_ZONES", value=str(len(additional_zone))
        ))

        # primary zone domain URL environmental variables
        env_vars.append(EnvVarArgs(
            name="URL", value=data.get("domain")
        ))

        # conf and gcp info for additional zones
        additional_zones = data.get("additional_kasm_zone") or []
        zone_output_list = []
        gcp_project = gcp_config.get("project")
        for zone_index in range(len(additional_zones)):
            zone_config = additional_zones[zone_index]

            subnet = gcp_network.additional_zone_subnet[zone_index].name
            zone_info = pulumi.Output.all(
                name=zone_config["name"],
                region=zone_config["region"],
                zone=zone_config["zone"],
                agent_size=zone_config["agent_size"],
                project=gcp_project,
                subnet=subnet
            ).apply(lambda args: {
                "name": args["name"],
                "region": args["region"],
                "zone": args["zone"],
                "agent_size": args["agent_size"],
                "max_instance": "10",
                "subnet": f"projects/{args['project']}/regions/{args['region']}/subnetworks/{args['subnet']}"
            })
            zone_output_list.append(zone_info)
        additional_zone_output = pulumi.Output.all(zone_output_list)

        # Get latest ubuntu noble image URL
        image = pulumi_gcp.compute.get_image(family="ubuntu-2404-lts-amd64",
                                             project="ubuntu-os-cloud")

        # final config and gcp info for all
        gcp_info = pulumi.Output.all(
            region=data.get("region"),
            zone=data.get("zone"),
            agent_size=data.get("agent_size"),
            agent_disk_size=data.get("agent_disk_size"),
            network=gcp_network.vpc.name,
            subnet=gcp_network.subnet.name,
            project=gcp_project,
            additional_zone=additional_zone_output,
            image=image.id
        ).apply(lambda args: {
            "region": args["region"],
            "zone": args["zone"],
            "agent_size": args["agent_size"],
            "agent_disk_size": args["agent_disk_size"],
            "network": f"projects/{args['project']}/global/networks/{args['network']}",
            "subnet": f"projects/{args['project']}/regions/{args['region']}/subnetworks/{args['subnet']}",
            "max_instance": "10",
            "project": args["project"],
            "image": args["image"],
            "additional_zone": args["additional_zone"]
        })

        gcp_info_json = gcp_info.apply(lambda info: json.dumps(info))
        env_vars.append(EnvVarArgs(
            name="GCP_INFO", value=gcp_info_json
        ))



        # cloud provider name
        env_vars.append(EnvVarArgs(
            name="CLOUD_PROVIDER", value="gcp"
        ))

        # total number of agents environmental variables
        total_agent = data.get("agent_number")
        for zone in additional_zone:
            total_agent = total_agent+zone["agent_number"]
        env_vars.append(EnvVarArgs(
            name="AGENT_NUMBER", value=str(total_agent)
        ))

        # admin password environmental variables, using secret ref
        env_vars.append(EnvVarArgs(
            name="ADMIN_PASS", value_from=EnvVarSourceArgs(
                secret_key_ref=SecretKeySelectorArgs(
                    name="kasm-secrets",
                    key="admin-password",
        ))))

        # SSL cert
        env_vars.append(EnvVarArgs(
            name="CERT", value_from=EnvVarSourceArgs(
                secret_key_ref=SecretKeySelectorArgs(
                    name="kasm-nginx-proxy-cert",
                    key="tls.crt",
                ))))
        env_vars.append(EnvVarArgs(
            name="CERT_KEY", value_from=EnvVarSourceArgs(
                secret_key_ref=SecretKeySelectorArgs(
                    name="kasm-nginx-proxy-cert",
                    key="tls.key",
                ))))



        # all agents' IP addresses environmental variable
        all_agent_list = []
        for agent in kasm_agent.agent_vm:
            all_agent_list.append(agent.network_interfaces[0].network_ip)
        for zone in list(kasm_agent.additional_zone_agents.values()):
            for agent in zone:
                all_agent_list.append(agent.network_interfaces[0].network_ip)
        env_vars.append(
            EnvVarArgs(
                name="AGENT_LIST",
                value=pulumi.Output.all(*all_agent_list).apply(
                    lambda *args: " ".join(str(item) for item in args)  # Convert each item to string before joining
                )
        ))

        # bash script for config job
        self.script = ConfigMap("kasm-config-script",
                                metadata={
                                    "name": "kasm-config-script",
                                    "namespace": "kasm"
                                },
                                data={
                                    "kasm_config.sh": get_kasm_config_configmap()
                                },
                                opts=pulumi.ResourceOptions(provider=gcp_cluster.cluster_provider,
                                                            depends_on=[kasm_helm.helm])

        )

        # Kuberentes job to configure Kasm, this includes enable agents, configuring zones and group settings
        self.job = Job(
            "kasm-config",
            metadata={
                "name": "kasm-config",
                "namespace": "kasm",
                "annotations": {
                    "pulumi.com/skipAwait": "true"
                }
            },
            spec=JobSpecArgs(
                backoff_limit=4,
                template=PodTemplateSpecArgs(
                    spec=PodSpecArgs(
                        containers=[ContainerArgs(
                            name="kasm-config-container",
                            image="ubuntu:25.04",
                            command=["/bin/bash", "-c", get_kasm_config_script()],
                            env=env_vars,
                            volume_mounts=[{
                                "name": "kasm-config-script",
                                "mountPath": "/tmp/kasm_config.sh",
                                "sub_path":"kasm_config.sh"
                            }]
                        )],
                        restart_policy="Never",
                        volumes=[{
                            "name": "kasm-config-script",
                            "configMap": {"name": "kasm-config-script"},
                        }]
                    )
                ),
            ),
            opts=pulumi.ResourceOptions(provider=gcp_cluster.cluster_provider,
                                        depends_on=[kasm_helm.helm, self.script],
                                        ignore_changes=["spec"])
        )