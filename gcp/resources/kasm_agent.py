from pulumi import Config, ResourceOptions, Output, CustomTimeouts
from pulumi_gcp.compute import (Instance, InstanceGroup, HttpsHealthCheck, BackendService, URLMap, TargetHttpsProxy,
                                GlobalForwardingRule, RegionBackendService)
import pulumi

config = Config()
data = config.require_object("data")
gcp_config = Config("gcp")


class SetupKasmAgent:
    def __init__(self, gcp_network, kasm_helm, get_agent_startup_script, get_proxy_startup_script):

        # Get the Agent Startup script
        agent_startup_script = get_agent_startup_script(agent_swap_size=4,
                                            kasm_build_url="https://kasm-static-content.s3.amazonaws.com/kasm_release_1.17.0.bbc15c.tar.gz",
                                            manager_url= data.get("domain"),
                                            manager_token=kasm_helm.manager_token)

        # Create Agent VMs For The Primary Zone
        self.agent_vm = []
        for agent_index in range(1, int(data.get("agent_number"))+1):
            agent = Instance(f"kasm-primary-zone-agent-{agent_index}",
                               network_interfaces=[{
                                   "network": gcp_network.vpc.id,
                                   "subnetwork": gcp_network.subnet.id
                               }],
                               name=f"kasm-primary-zone-agent-{agent_index}",
                               machine_type=data.get("agent_size"),
                               zone=data.get("zone"),
                               boot_disk={
                                   "initialize_params": {
                                       "image": "ubuntu-2404-noble-amd64-v20250228",
                                       "size": data.get("agent_disk_size"),
                                   },
                               },
                               metadata_startup_script=agent_startup_script,
                               opts=ResourceOptions(
                                   depends_on=[kasm_helm.helm])
                               )
            self.agent_vm.append(agent)


        additional_zones = data.get("additional_kasm_zone") or []
        self.additional_zone_agents = {}
        self.additional_zone_proxies = []
        self.addition_zone_proxy_lbs = []
        for zone_index in range(2, len(data.get("additional_kasm_zone") or [])+2):
            # Create Agent VMs For Additional Zones
            zone_config = additional_zones[zone_index-2]
            self.additional_zone_agents[zone_config["name"]] = []
            agent_startup_script = get_agent_startup_script(agent_swap_size=4,
                                                kasm_build_url="https://kasm-static-content.s3.amazonaws.com/kasm_release_1.17.0.bbc15c.tar.gz",
                                                manager_url= zone_config["domain"],
                                                manager_token=kasm_helm.manager_token)
            for agent_index in range(1, int(zone_config["agent_number"])+1):
                agent = Instance(f'kasm-{zone_config["name"]}-agent-{agent_index}',
                                 name=f'kasm-{zone_config["name"]}-agent-{agent_index}',
                                 network_interfaces=[{
                                     "network": gcp_network.vpc.id,
                                     "subnetwork": gcp_network.additional_zone_subnet[zone_index-2].id
                                 }],
                                 machine_type=zone_config["agent_size"],
                                 zone=zone_config["zone"],
                                 boot_disk={
                                     "initialize_params": {
                                         "image": "ubuntu-2404-noble-amd64-v20250228",
                                         "size": data.get("agent_disk_size"),
                                     },
                                 },
                                 metadata_startup_script=agent_startup_script,
                                 opts=ResourceOptions(
                                     depends_on=[kasm_helm.helm])
                                 )
                self.additional_zone_agents[zone_config["name"]] .append(agent)

            # Create Proxy VM For Additional Zones
            proxy_startup_script = get_proxy_startup_script(data.get("domain"), kasm_helm.service_token, zone_config["name"], kasm_helm.tls_crt, kasm_helm.tls_key)
            proxy = Instance(f'kasm-{zone_config["name"]}-proxy',
                             name=f'kasm-{zone_config["name"]}-proxy',
                             network_interfaces=[{
                                 "access_configs": [{}],
                                 "network": gcp_network.vpc.id,
                                 "subnetwork": gcp_network.additional_zone_subnet[zone_index-2].id,
                             }],
                             machine_type=zone_config["proxy_size"],
                             zone=zone_config["zone"],
                             boot_disk={
                                 "initialize_params": {
                                     "image": "ubuntu-2404-noble-amd64-v20250228",
                                     "size": 50,
                                 },
                             },
                             metadata_startup_script=proxy_startup_script,
                             can_ip_forward=True,
                             tags=["kasm-proxy"],
                             opts=ResourceOptions(
                                 depends_on=[kasm_helm.helm, kasm_helm.kasm_secrets])
                             )

            # GCP instance group for proxy load balancer
            instance_group = InstanceGroup(f"kasm-proxy-{zone_config['name']}-instance-group",
                                           name = f"kasm-proxy-{zone_config['name']}-instance-group",
                                           network = gcp_network.vpc.id,
                                           zone = zone_config['zone'],
                                           named_ports=[{
                                               "name": "https",
                                               "port": 443,
                                           }],
                                           instances = [proxy.id]
            )

            # GCP https health check for proxy load balancer
            health_check = HttpsHealthCheck(f"kasm-proxy-{zone_config['name']}-healthcheck",
                                           name=f"kasm-proxy-{zone_config['name']}-healthcheck",
                                           request_path="/checkvalid",
                                           port=443,
                                           timeout_sec=1,
                                           check_interval_sec=60)

            # GCP backend service check for proxy load balancer
            backend_service = BackendService(f"kasm-{zone_config['name']}-backend-service",
                                                         name=f"kasm-{zone_config['name']}-backend-service",
                                                         protocol="HTTPS",
                                                         port_name="https",
                                                         health_checks=health_check.id,
                                                         backends=[{
                                                             "group": instance_group.id,
                                                         }],
                                                         connection_draining_timeout_sec=60,
                                                         timeout_sec=28800,
                                                         )

            # GCP URL map/application load balancer
            url_map = URLMap(f"kasm-{zone_config['name']}-url-map",
                                         name=f"kasm-{zone_config['name']}-url-map",
                                         default_service=backend_service.id,
                                         )

            # GCP target https proxy for proxy load balancer
            target_https_proxy = TargetHttpsProxy(f"kasm-{zone_config['name']}-target-https-proxy",
                                                              name=f"kasm-{zone_config['name']}-target-https-proxy",
                                                              url_map=url_map.id,
                                                              ssl_certificates=[gcp_network.kasm_cert.id],
                                                              )

            # GCP forward rule for proxy load balancer
            forwarding_rule = GlobalForwardingRule(f"kasm-{zone_config['name']}-forwarding-rule",
                                                               name=f"kasm-{zone_config['name']}-forwarding-rule",
                                                               ip_address=gcp_network.additional_zone_proxy_lb_public_ip_address[zone_index-2].address,
                                                               port_range="443",
                                                               target=target_https_proxy.id,
                                                               load_balancing_scheme="EXTERNAL",
                                                               ip_protocol="TCP"
                                                               )


            self.additional_zone_proxies.append(proxy)
