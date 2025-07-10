from pulumi import Config, ResourceOptions, Output, CustomTimeouts
import pulumi_aws as aws
import pulumi

config = Config()
data = config.require_object("data")
gcp_config = Config("gcp")


class SetupKasmAgent:
    def __init__(self, kasm_primary_zone_aws_provider, public_route_53_zone, aws_network, kasm_helm, get_agent_startup_script, get_proxy_startup_script, ssh_key):

        # Get the Agent Startup script
        agent_startup_script = get_agent_startup_script(agent_swap_size=4,
                                            kasm_build_url="https://kasm-static-content.s3.amazonaws.com/kasm_release_1.17.0.bbc15c.tar.gz",
                                            manager_url= data.get("domain"),
                                            manager_token=kasm_helm.manager_token)

        # Create AWS Key pairs using the generated SSH key
        self.ec2_keypair = aws.ec2.KeyPair("kasm-vm-ssh-keypair",
                                   key_name="kasm-vm-ssh-keypair",
                                   public_key=ssh_key.ssh_key.public_key_openssh,
                                           opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        # Create Agent VMs For The Primary Zone
        self.agent_vm = []
        self.network_interface = []
        self.agent_instance_type = aws.ec2.InstanceType(data.get("agent_size"))
        self.ubuntu_ami = aws.ec2.get_ami(most_recent=True,
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

        for agent_index in range(1, int(data.get("agent_number"))+1):
            # Create Network Interface for the Agent VM
            agent_network_interface = aws.ec2.NetworkInterface(f"kasm-primary-zone-agent-{agent_index}-network-interface",
                                                                           subnet_id=aws_network.private_subnet.id,
                                                                           security_groups=[aws_network.sg.id],
                                                                           tags={
                                                                               "Name": f"kasm-primary-zone-agent-{agent_index}-network-interface",
                                                                           },
                                                                           opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider,
                                                                                                       depends_on=[kasm_helm.helm]))
            # Create Agent VM
            agent = aws.ec2.Instance(f"kasm-primary-zone-agent-{agent_index}",
                                   ami=self.ubuntu_ami.id,
                                   instance_type=self.agent_instance_type,
                                   tags={
                                       "Name": f"kasm-primary-zone-agent-{agent_index}",
                                   },
                                   network_interfaces=[{
                                       "network_interface_id": agent_network_interface,
                                       "device_index": 0,
                                   }],
                                   root_block_device={
                                       "volume_size": data.get("agent_disk_size"),
                                       "volume_type": "gp3",
                                       "delete_on_termination": True
                                   },
                                   key_name= self.ec2_keypair.key_name,
                                   user_data = agent_startup_script,
                                   opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider,
                                                               ignore_changes=["ami"],
                                                               depends_on=[kasm_helm.helm])
                                   )
            self.network_interface.append(agent_network_interface)
            self.agent_vm.append(agent)


        # Create Agent and Proxy VMs For Additional Zones
        additional_zones = data.get("additional_kasm_zone") or []
        self.additional_zone_agents = {}
        self.additional_zone_agent_network_interfaces = {}
        self.additional_zone_proxies = []
        self.additional_zone_proxy_network_interfaces = []
        self.additional_zone_proxy_alb = []
        self.additional_zone_proxy_target_group = []
        self.additional_zone_proxy_target_group_attachment = []
        self.additional_zone_proxy_alb_listener = []
        self.additional_zone_proxy_record = []
        self.additional_zone_ubuntu_ami = {}
        self.additional_zone_ec2_key_pair = {}
        for zone_index in range(2, len(data.get("additional_kasm_zone") or [])+2):
            zone_config = additional_zones[zone_index-2]
            zone_name = zone_config["name"]
            provider = aws_network.additional_zone_resources[zone_name]["provider"]
            self.additional_zone_agents[zone_name] = []
            self.additional_zone_agent_network_interfaces[zone_name] = []

            agent_startup_script = get_agent_startup_script(agent_swap_size=4,
                                                kasm_build_url="https://kasm-static-content.s3.amazonaws.com/kasm_release_1.17.0.bbc15c.tar.gz",
                                                manager_url= zone_config["domain"],
                                                manager_token=kasm_helm.manager_token)

            agent_instance_type = aws.ec2.InstanceType(data.get("agent_size"))

            # Create AWS Key pairs using the generated SSH key
            ec2_keypair = aws.ec2.KeyPair(f"kasm-vm-{zone_config['name']}-ssh-keypair",
                                          key_name=f"kasm-vm-{zone_config['name']}-ssh-keypair",
                                          public_key=ssh_key.ssh_key.public_key_openssh,
                                          opts=pulumi.ResourceOptions(provider=provider))
            self.additional_zone_ec2_key_pair[zone_name] = ec2_keypair

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
                                         opts=pulumi.InvokeOptions(provider=provider)
                                         )
            self.additional_zone_ubuntu_ami[zone_name] = ubuntu_ami

            for agent_index in range(1, int(zone_config["agent_number"])+1):
                # Create Network Interface for the Agent VM
                agent_network_interface = aws.ec2.NetworkInterface(f"kasm-{zone_config['name']}-zone-agent-{agent_index}-network-interface",
                                                             subnet_id=aws_network.additional_zone_resources[zone_name]["private_subnet"].id,
                                                             security_groups=[aws_network.additional_zone_resources[zone_name]["sg"].id],
                                                             tags={
                                                                 "Name": f"kasm-{zone_config['name']}-zone-agent-{agent_index}-network-interface",
                                                             },
                                                             opts=pulumi.ResourceOptions(provider=provider,
                                                                                         depends_on=[kasm_helm.helm]))

                # Create Agent VM
                agent = aws.ec2.Instance(f"kasm-{zone_name}-zone-agent-{agent_index}",
                                         ami=ubuntu_ami.id,
                                         instance_type=agent_instance_type,
                                         tags={
                                             "Name": f"kasm-{zone_name}-zone-agent-{agent_index}",
                                         },
                                         key_name=ec2_keypair.key_name,
                                         network_interfaces=[{
                                             "network_interface_id": agent_network_interface,
                                             "device_index": 0,
                                         }],
                                         root_block_device={
                                             "volume_size": data.get("agent_disk_size"),
                                             "volume_type": "gp3",
                                             "delete_on_termination": True
                                         },
                                         user_data = agent_startup_script,
                                         opts=pulumi.ResourceOptions(provider=provider,
                                                                     ignore_changes=["ami"],
                                                                     depends_on=[kasm_helm.helm])
                                         )
                self.additional_zone_agent_network_interfaces[zone_name].append(agent_network_interface)
                self.additional_zone_agents[zone_name].append(agent)

            proxy_startup_script = get_proxy_startup_script(data.get("domain"), kasm_helm.service_token, zone_name, kasm_helm.tls_crt, kasm_helm.tls_key)

            # Create Network Interface for the Proxy VM
            proxy_network_interface = aws.ec2.NetworkInterface(f"kasm-{zone_config['name']}-zone-proxy-network-interface",
                                                               subnet_id=aws_network.additional_zone_resources[zone_name]["private_subnet"].id,
                                                               security_groups=[aws_network.additional_zone_resources[zone_name]["sg"].id],
                                                               tags={
                                                                   "Name": f"kasm-{zone_config['name']}-zone-proxy-network-interface",
                                                               },
                                                               opts=pulumi.ResourceOptions(provider=provider,
                                                                                           depends_on=[kasm_helm.helm]))
            # Create Proxy VM
            proxy = aws.ec2.Instance(f"kasm-{zone_name}-proxy",
                                     ami=ubuntu_ami.id,
                                     instance_type=zone_config["proxy_size"],
                                     tags={
                                         "Name": f"kasm-{zone_name}-proxy",
                                     },
                                     network_interfaces=[{
                                         "network_interface_id": proxy_network_interface,
                                         "device_index": 0,
                                     }],
                                     key_name=ec2_keypair.key_name,
                                     root_block_device={
                                         "volume_size": 50,
                                         "volume_type": "gp3",
                                         "delete_on_termination": True
                                     },
                                     user_data = proxy_startup_script,
                                     opts=pulumi.ResourceOptions(provider=provider,
                                                                 ignore_changes=["ami"],
                                                                 depends_on=[kasm_helm.helm])
                                     )
            self.additional_zone_proxies.append(proxy)
            self.additional_zone_proxy_network_interfaces.append(proxy_network_interface)

            # Create AWS ALB for Dedicated Kasm Proxy
            proxy_alb = aws.lb.LoadBalancer(f"kasm-{zone_name}-proxy-alb",
                                            name=f"kasm-{zone_name}-proxy-alb",
                                            internal=False,
                                            load_balancer_type="application",
                                            security_groups=[aws_network.additional_zone_resources[zone_name]["sg"].id],
                                            subnets=[aws_network.additional_zone_resources[zone_name]["public_subnet"].id,
                                                     aws_network.additional_zone_resources[zone_name]["additional_public_subnet"].id,],
                                            opts=pulumi.ResourceOptions(provider=provider,
                                                                        depends_on=[kasm_helm.helm]))

            # Create AWS Target Group for Dedicated Kasm Proxy
            proxy_target_group = aws.lb.TargetGroup(f"kasm-{zone_name}-proxy-tg",
                                              port=443,
                                              protocol="HTTPS",
                                              target_type="instance",
                                              vpc_id=aws_network.additional_zone_resources[zone_name]["vpc"].id,
                                              tags={"Name": f"kasm-{zone_name}-proxy-tg"},
                                              health_check= {
                                                  "enabled": True,
                                                  "healthy_threshold": 2,
                                                  "interval": 15,
                                                  "matcher": "200",
                                                  "path": "/checkvalid",
                                                  "port": "443",
                                                  "protocol": "HTTPS",
                                                  "timeout": 5,
                                                  "unhealthy_threshold": 2,
                                              },
                                              opts=pulumi.ResourceOptions(provider=provider,
                                                                          depends_on=[kasm_helm.helm])
                                              )

            # Create AWS Target Group Attachment for Dedicated Kasm Proxy
            proxy_target_group_attachment = aws.lb.TargetGroupAttachment(f"kasm-{zone_name}-tg-attachment",
                                                                         target_group_arn=proxy_target_group.arn,
                                                                         target_id=proxy.id,
                                                                         port=443,
                                                                         opts=pulumi.ResourceOptions(provider=provider,
                                                                                                     depends_on=[kasm_helm.helm])
                                                                         )
            # Create AWS Listener for Dedicated Kasm Proxy
            proxy_alb_listener = aws.lb.Listener(f"kasm-{zone_name}-proxy-listener",
                                       load_balancer_arn=proxy_alb.arn,
                                       port=443,
                                       protocol="HTTPS",
                                       ssl_policy="ELBSecurityPolicy-2016-08",
                                       certificate_arn=aws_network.additional_zone_resources[zone_name]["cert"].arn,
                                       default_actions=[aws.lb.ListenerDefaultActionArgs(
                                           type="forward",
                                           target_group_arn=proxy_target_group.arn
                                       )],
                                       opts=pulumi.ResourceOptions(provider=provider,
                                                                   depends_on=[kasm_helm.helm])
                                       )

            self.additional_zone_proxy_alb.append(proxy_alb)
            self.additional_zone_proxy_target_group.append(proxy_target_group)
            self.additional_zone_proxy_target_group_attachment.append(proxy_target_group_attachment)
            self.additional_zone_proxy_alb_listener.append(proxy_alb_listener)


            # Create DNS Record for Dedicated Kasm Proxy
            elb_hosted_zone_id = aws.elb.get_hosted_zone_id(zone_config["region"]).id
            kasm_proxy_record = aws.route53.Record(f"kasm-{zone_name}-zone-proxy-record",
                                                             zone_id=public_route_53_zone.zone_id,
                                                             name=zone_config["proxy_domain"],
                                                             type=aws.route53.RecordType.A,
                                                             aliases=[{
                                                                 "name": proxy_alb.dns_name,
                                                                 "zone_id": elb_hosted_zone_id,
                                                                 "evaluate_target_health": True,
                                                             }],
                                                             opts=pulumi.ResourceOptions(
                                                                 depends_on=[kasm_helm.helm, kasm_helm.kasm_ingress],
                                                             ))
            self.additional_zone_proxy_record.append(kasm_proxy_record)