from pulumi import Config, ResourceOptions
from pulumi_gcp.compute import Network, Subnetwork, Router, RouterNat, GlobalAddress, Firewall, Address, ManagedSslCertificate
from pulumi_gcp.dns import ManagedZone, ManagedZonePrivateVisibilityConfigArgs, \
    ManagedZonePrivateVisibilityConfigNetworkArgs, RecordSet, get_managed_zone
from pulumi_gcp.servicenetworking import Connection
import pulumi

config = Config()
data = config.require_object("data")


class SetupGcpNetwork:
    def __init__(self, gcp_api):
        ## if auto_enable_gcp_api is configured to true
        if gcp_api:
            # Create an VPC with depends on GCP APIs enablement
            self.vpc = Network(
                f"kasm",
                name=f"kasm",
                auto_create_subnetworks=False,
                opts=ResourceOptions(
                    depends_on=[gcp_api.gcp_compute_api,
                                gcp_api.gcp_container_api,
                                gcp_api.gcp_dns_api,
                                gcp_api.gcp_servicenetworking_api,
                                gcp_api.gcp_sqladmin_api])
            )
        else:
            self.vpc = Network(
                f"kasm",
                name=f"kasm",
                auto_create_subnetworks=False,
            )

        # Create a Subnet
        self.subnet = Subnetwork(f"kasm-primary-zone-subnet",
                                 name=f"kasm-primary-zone-subnet",
                                 ip_cidr_range="10.0.1.0/24",
                                 region=f'{data.get("region")}',
                                 network=self.vpc.id,
                                 )

        # Create a Cloud Router
        self.router = Router(f"kasm-primary-zone-router",
                             name=f"kasm-primary-zone-router",
                             network=self.vpc.id,
                             region=data.get('region')
                             )
        # Create a Cloud NAT
        self.nat = RouterNat(f"kasm-primary-zone-nat",
                             name=f"kasm-primary-zone-nat",
                             router=self.router.name,
                             nat_ip_allocate_option="AUTO_ONLY",
                             source_subnetwork_ip_ranges_to_nat="ALL_SUBNETWORKS_ALL_IP_RANGES",
                             region=data.get('region'),
                             log_config={
                                 "enable": True,
                                 "filter": "ERRORS_ONLY"
                             })

        # Firewall for SSH
        if data.get("vm_enable_ssh"):
            self.compute_ssh_firewall = Firewall(
                f"kasm-enable-ssh-firewall",
                name=f"kasm-enable-ssh-firewall",
                network=self.vpc.self_link,
                allows=[{
                    "protocol": "tcp",
                    "ports": ["22"]
                }],
                source_ranges=["0.0.0.0/0"]
            )

        # Firewall Internal for HTTPS
        self.compute_internal_https_firewall = Firewall(
            f"kasm-enable-internal-https-firewall",
            name=f"kasm-enable-internal-https-firewall",
            network=self.vpc.self_link,
            allows=[{
                "protocol": "tcp",
                "ports": ["443"]
            }],
            source_ranges=["10.0.0.0/8"]
        )

        # Firewall 443 For GCP Load Balancer
        self.compute_gcp_lb_healthcheck_firewall = Firewall(
            f"kasm-enable-gcp-lb-healthcheck-https",
            name=f"kasm-enable-gcp-lb-healthcheck-https",
            network=self.vpc.self_link,
            allows=[{
                "protocol": "tcp",
                "ports": ["443"]
            }],
            target_tags = ["kasm-proxy"],
            # these two IPs are GCP loadbalancer request and health check ranges, see GCP docs https://cloud.google.com/load-balancing/docs/https#firewall-rules
            source_ranges=["35.191.0.0/16", "130.211.0.0/22"]
        )

        #  Private DNS zone for DB
        self.private_zone = ManagedZone(f"kasm-private-zone",
                                        name=f"kasm-private-zone",
                                        dns_name=f"kasm.int.",
                                        description=f"kasm Private DNS zone",
                                        visibility="private",
                                        private_visibility_config=ManagedZonePrivateVisibilityConfigArgs(
                                            networks=[
                                                ManagedZonePrivateVisibilityConfigNetworkArgs(
                                                    network_url=self.vpc.id,
                                                )
                                            ],
                                        ),
                                        opts=ResourceOptions(
                                            depends_on=[self.vpc]
                                        ))

        # private IP for DB
        self.private_ip_address = GlobalAddress(f"kasm-db-private-ip",
                                                name=f"kasm-db-private-ip",
                                                purpose="VPC_PEERING",
                                                address="10.1.0.0",
                                                address_type="INTERNAL",
                                                prefix_length=16,
                                                network=self.vpc.id)

        # Public IP for GKE Ingress Load Balancer
        self.public_ip_address = GlobalAddress("kasm-primary-zone-loadbalancer-ip",
                                               name="kasm-primary-zone-loadbalancer-ip",
                                               opts=ResourceOptions(
                                                   depends_on=[self.vpc]
                                               ))

        # Create or get the GCP Cloud DNS zone
        self.dns = ""
        if data.get("cloud_dns_zone")["create"]:
            self.dns = ManagedZone("kasm-public-zone",
                                               name="kasm-public-zone",
                                               dns_name=f"{data.get('cloud_dns_zone')['zone_dns_name']}",
                                               description="Kasm public DNS zone",
                                               opts=ResourceOptions(
                                                    depends_on=[self.vpc]
                                               ))
        else:
            self.dns = ManagedZone.get("kasm-public-zone", data.get("cloud_dns_zone")["zone_name"])

        ## Adding recordset entry
        self.record_set = RecordSet("kasm-primary-zone-record-set",
                          name=f'{data.get("domain")}.',
                          type="A",
                          ttl=300,
                          managed_zone=self.dns.name,
                          rrdatas=[self.public_ip_address.address],
                          opts=ResourceOptions(
                               depends_on=[self.vpc]
                        ))


        # Create the Private Connection to DB address
        self.private_vpc_connection = Connection(f"kasm-db-connection",
                                                 network=self.vpc.id,
                                                 service="servicenetworking.googleapis.com",
                                                 deletion_policy="ABANDON",
                                                 reserved_peering_ranges=[
                                                     self.private_ip_address.name],
                                                 )

        self.domains = [data.get("domain")]

        # Additional Zone Resources
        additional_zones = data.get("additional_kasm_zone") or []
        self.additional_zone_public_ip_address = []
        self.additional_zone_proxy_lb_public_ip_address=[]
        self.additional_zone_subnet=[]
        self.additional_zone_router=[]
        self.additional_zone_nat=[]
        for zone_index in range(2, len(data.get("additional_kasm_zone") or [])+2):
            zone_config = additional_zones[zone_index-2]
            self.domains.append(zone_config["domain"])
            self.domains.append(zone_config["proxy_domain"])
            # Additional Zone Subnet
            subnet = Subnetwork(f'kasm-{zone_config["name"]}-subnet',
                                     name=f'kasm-{zone_config["name"]}-subnet',
                                     ip_cidr_range=f"10.0.{zone_index}.0/24",
                                     region=f'{zone_config["region"]}',
                                     network=self.vpc.id,
                                     )
            self.additional_zone_subnet.append(subnet)

            # Additional Zone Cloud Router
            router = Router(f'kasm-{zone_config["name"]}-router',
                                 name=f'kasm-{zone_config["name"]}-router',
                                 network=self.vpc.id,
                                 region=zone_config["region"]
                                 )
            self.additional_zone_router.append(router)

            # Additional Zone Cloud NAT
            nat = RouterNat(f'kasm-{zone_config["name"]}-nat',
                                 name=f'kasm-{zone_config["name"]}-nat',
                                 router=router.name,
                                 nat_ip_allocate_option="AUTO_ONLY",
                                 source_subnetwork_ip_ranges_to_nat="ALL_SUBNETWORKS_ALL_IP_RANGES",
                                 region=zone_config["region"],
                                 log_config={
                                     "enable": True,
                                     "filter": "ERRORS_ONLY"
                                 })
            self.additional_zone_nat.append(nat)

            # Additional Zone Public IP for GKE Ingress Load Balancer
            public_ip_address = GlobalAddress(f'kasm-{zone_config["name"]}-loadbalancer-ip',
                                              name=f'kasm-{zone_config["name"]}-loadbalancer-ip',
                                              opts=ResourceOptions(
                                                  depends_on=[self.vpc]
                                              ))
            self.additional_zone_public_ip_address.append(public_ip_address)

            # additional zone ingress load balancer record
            self.record_set =RecordSet(f'kasm-{zone_config["name"]}-record-set',
                                       name=f'{zone_config["domain"]}.',
                                       type="A",
                                       ttl=300,
                                       managed_zone=self.dns.name,
                                       rrdatas=[public_ip_address.address],
                                       opts=ResourceOptions(
                                           depends_on=[self.vpc])
                                       )

            # Additional Zone Public IP for Kasm Proxy
            proxy_lb_public_ip_address = GlobalAddress(f'kasm-{zone_config["name"]}-proxy-lb-public-ip',
                                              name=f'kasm-{zone_config["name"]}-proxy-lb-public-ip',
                                              opts=ResourceOptions(
                                                  depends_on=[self.vpc]
                                              ))
            self.additional_zone_proxy_lb_public_ip_address.append(proxy_lb_public_ip_address)

            # additional zone proxy load balancer record
            self.record_set =RecordSet(f'kasm-{zone_config["name"]}-proxy-record-set',
                                       name=f'{zone_config["proxy_domain"]}.',
                                       type="A",
                                       ttl=300,
                                       managed_zone=self.dns.name,
                                       rrdatas=[proxy_lb_public_ip_address.address],
                                       opts=ResourceOptions(
                                           depends_on=[self.vpc])
                                       )

        # GCP managed cert covering all the defined domains
        self.kasm_cert = ManagedSslCertificate("kasm-cert",
                                                 name="kasm-cert",
                                                 managed={
                                                     "domains": self.domains,
                                                 })




