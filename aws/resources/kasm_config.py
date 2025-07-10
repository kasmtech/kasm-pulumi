from pulumi import Config
from pulumi_kubernetes.batch.v1 import Job, JobSpecArgs
from pulumi_kubernetes.core.v1 import PodTemplateSpecArgs, PodSpecArgs, ContainerArgs, EnvVarArgs, EnvVarSourceArgs, SecretKeySelectorArgs, ConfigMap
import pulumi
import pulumi_aws as aws
import json



config = Config()
data = config.require_object("data")
secrets = config.require_secret_object("data")
additional_zone = data.get("additional_kasm_zone") or []


class KasmConfig:
    def __init__(self, kasm_primary_zone_aws_provider, aws_network, eks, kasm_helm, kasm_agent, ssh_key, get_kasm_config_script, get_kasm_config_configmap):

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

        # conf and aws info for additional zones
        additional_zones = data.get("additional_kasm_zone") or []
        zone_output_list = []
        for zone_index in range(len(additional_zones)):
            zone_config = additional_zones[zone_index]
            zone_name = zone_config["name"]

            # subnet for autoscaler configuration
            subnet = aws_network.additional_zone_resources[zone_name]["private_subnet"]

            zone_info = pulumi.Output.all(
                name=zone_config["name"],
                region=zone_config["region"],
                aws_ec2_instance_type=zone_config["agent_size"],
                aws_ec2_subnet_id=subnet.id,
                aws_ec2_security_group_ids=aws_network.additional_zone_resources[zone_name]["sg"].id,
                aws_ec2_ami_id=kasm_agent.additional_zone_ubuntu_ami[zone_name].id
            ).apply(lambda args: {
                "name": args["name"],
                "region": args["region"],
                "aws_ec2_instance_type": args["aws_ec2_instance_type"],
                "max_instance": "10",
                "aws_ec2_subnet_id": args["aws_ec2_subnet_id"],
                "aws_ec2_security_group_ids": [args["aws_ec2_security_group_ids"]],
                "aws_ec2_ami_id": args["aws_ec2_ami_id"]
            })
            zone_output_list.append(zone_info)
        additional_zone_output = pulumi.Output.all(zone_output_list)

        # Get latest ubuntu noble image URL
        ubuntu_ami = aws.ec2.get_ami(most_recent=True,
                                                  filters=[
                                                      {
                                                          "name": "name",
                                                          "values": ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"],
                                                      },
                                                      {
                                                          "name": "virtualization-type",
                                                          "values": ["hvm"],
                                                      },
                                                  ],
                                                  owners=["099720109477"],
                                                  opts=pulumi.InvokeOptions(provider=kasm_primary_zone_aws_provider)
                                                  )

        # Create the IAM role policy for Kasm Autoscaler
        self.default_role_policy = aws.iam.get_policy_document(statements=[{
            "actions": ["sts:AssumeRole"],
            "principals": [{
                "type": "Service",
                "identifiers": ["ec2.amazonaws.com"]
            }],
        }])

        # Create the IAM role for Kasm Autoscaler
        self.default_autoscaler_ec2_role = aws.iam.Role("kasm-default-autoscaler-ec2-role",
                                name="kasm-default-autoscaler-ec2-role",
                                assume_role_policy=self.default_role_policy.json,
                                opts=pulumi.ResourceOptions(depends_on=[kasm_helm.helm])
                                )

        # Create the IAM instance profile for Kasm Autoscaler
        self.default_autoscaler_ec2_profile = aws.iam.InstanceProfile("kasm-default-autoscaler-ec2-profile",
                                                       name="kasm-default-autoscaler-ec2-profile",
                                                       role=self.default_autoscaler_ec2_role.name,
                                                       opts=pulumi.ResourceOptions(depends_on=[kasm_helm.helm])
                                                       )

        # Final config and aws info for all
        aws_info = pulumi.Output.all(
            region=data.get("region"),
            aws_ec2_instance_type=data.get("agent_size"),
            aws_ec2_ebs_volume_size_gb=data.get("agent_disk_size"),
            aws_ec2_subnet_id=aws_network.private_subnet.id,
            additional_zone=additional_zone_output,
            aws_ec2_ami_id=ubuntu_ami.id,
            aws_ec2_security_group_ids=aws_network.sg.id,
            aws_ec2_iam = self.default_autoscaler_ec2_profile.name
        ).apply(lambda args: {
            "region": args["region"],
            "aws_ec2_instance_type": args["aws_ec2_instance_type"],
            "aws_ec2_ebs_volume_size_gb": args["aws_ec2_ebs_volume_size_gb"],
            "aws_ec2_subnet_id": args["aws_ec2_subnet_id"],
            "max_instance": "10",
            "aws_ec2_ami_id": args["aws_ec2_ami_id"],
            "additional_zone": args["additional_zone"],
            "aws_ec2_security_group_ids": [args["aws_ec2_security_group_ids"]],
            "aws_ec2_iam": args["aws_ec2_iam"]
        })

        aws_info_json = aws_info.apply(lambda info: json.dumps(info))
        env_vars.append(EnvVarArgs(
            name="AWS_INFO", value=aws_info_json
        ))


        # cloud provider name
        env_vars.append(EnvVarArgs(
            name="CLOUD_PROVIDER", value="aws"
        ))

        # ssh key for Kasm autoscaler
        env_vars.append(EnvVarArgs(
            name="SSH_PRIVATE_KEY_PEM", value=ssh_key.ssh_key.private_key_pem.apply(lambda key: key.replace('\n', '\\n')),
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


        # all agents' IP addresses environmental variable
        all_agent_list = []
        for agent in kasm_agent.agent_vm:
            all_agent_list.append(agent.private_ip)
        for zone in list(kasm_agent.additional_zone_agents.values()):
            for agent in zone:
                all_agent_list.append(agent.private_ip)
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
                                opts=pulumi.ResourceOptions(provider=eks.k8s_provider,
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
            opts=pulumi.ResourceOptions(provider=eks.k8s_provider,
                                        depends_on=[kasm_helm.helm, self.script],
                                        ignore_changes=["spec"])
        )