from pulumi import Config, ResourceOptions
import pulumi
import pulumi_aws as aws

config = Config()
data = config.require_object("data")


class SetupAwsNetwork:
    def __init__(self, kasm_primary_zone_aws_provider, public_route_53_zone):
        # Create a VPC
        self.vpc = aws.ec2.Vpc(
            "kasm-vpc",
            cidr_block="10.0.0.0/16",
            enable_dns_hostnames=True,
            enable_dns_support=True,
            tags={
                "Name": "kasm-vpc",
            },
            opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
        )

        # Create a Private Subnet
        self.private_subnet = aws.ec2.Subnet("kasm-private-subnet",
                                        vpc_id=self.vpc.id,
                                        cidr_block="10.0.0.0/24",
                                        availability_zone = f"{data.get('availability_zone')}",
                                        map_public_ip_on_launch=False,
                                        tags={
                                            "Name": "kasm-private-subnet",
                                            "kubernetes.io/role/internal-elb": "1",
                                        },
                                        opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        self.additional_private_subnet = aws.ec2.Subnet("kasm-additional-private-subnet",
                                                        vpc_id=self.vpc.id,
                                                        cidr_block="10.0.1.0/24",
                                                        availability_zone = f"{data.get('additional_availability_zone')}",
                                                        map_public_ip_on_launch=False,
                                                        tags={
                                                            "Name": "kasm-additional-private-subnet",
                                                            "kubernetes.io/role/internal-elb": "1",
                                                        },
                                                        opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        # Create a Public Subnet
        self.public_subnet = aws.ec2.Subnet("kasm-public-subnet",
                                       vpc_id=self.vpc.id,
                                       cidr_block="10.0.2.0/24",
                                       availability_zone = f"{data.get('availability_zone')}",
                                       map_public_ip_on_launch=True,
                                       tags={
                                           "Name": "kasm-public-subnet",
                                           "kubernetes.io/role/elb": "1",
                                       },
                                       opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        self.additional_public_subnet = aws.ec2.Subnet("kasm-additional-public-subnet",
                                            vpc_id=self.vpc.id,
                                            cidr_block="10.0.3.0/24",
                                            availability_zone = f"{data.get('additional_availability_zone')}",
                                            map_public_ip_on_launch=True,
                                            tags={
                                                "Name": "kasm-additional-public-subnet",
                                                "kubernetes.io/role/elb": "1",
                                            },
                                            opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        # Create Elastic IP
        self.eip = aws.ec2.Eip("kasm-nat-eip",
                               domain="vpc",
                               opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        self.additional_eip = aws.ec2.Eip("kasm-additional-nat-eip",
                               domain="vpc",
                               opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        # Create an Internet Gateway
        self.igw = aws.ec2.InternetGateway("kasm-igw",
                                      vpc_id=self.vpc.id,
                                      tags={
                                          "Name": "kasm-igw",
                                      },
                                      opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        # Create a NatGateway
        self.nat_gateway = aws.ec2.NatGateway("kasm-natgw",
                                         allocation_id=self.eip.allocation_id,
                                         subnet_id=self.public_subnet.id,
                                         tags={
                                             "Name": "kasm-natgw",
                                         },
                                         opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider,
                                                                     depends_on=[self.igw]))

        self.additional_nat_gateway = aws.ec2.NatGateway("kasm-additional-natgw",
                                              allocation_id=self.additional_eip.allocation_id,
                                              subnet_id=self.additional_public_subnet.id,
                                              tags={
                                                  "Name": "kasm-additional-natgw",
                                              },
                                              opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider,
                                                                          depends_on=[self.igw]))

        # Create a Public Route Table
        self.pub_route_table = aws.ec2.RouteTable("kasm-public-rt",
                                             vpc_id=self.vpc.id,
                                             tags={
                                                 "Name": "kasm-public-rt",
                                             },
                                             opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider,
                                                                         ignore_changes=["routes"]))

        # Route for outbound traffic
        self.default_public_route = aws.ec2.Route(
            "kasm-default-public-route",
            route_table_id=self.pub_route_table.id,
            destination_cidr_block="0.0.0.0/0",
            gateway_id=self.igw.id,
            opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
        )

        # Create a private Route Table
        self.prv_route_table = aws.ec2.RouteTable("kasm-private-rt",
                                             vpc_id=self.vpc.id,
                                             tags={
                                                 "Name": "kasm-private-rt",
                                             },
                                             opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

        # Route for outbound traffic
        self.default_private_route = aws.ec2.Route(
            "kasm-default-private-route",
            route_table_id=self.prv_route_table.id,
            destination_cidr_block="0.0.0.0/0",
            nat_gateway_id=self.nat_gateway.id,
            opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
        )

        # Create a Public Route Association
        self.pub_rt_association = aws.ec2.RouteTableAssociation("kasm-public-rt-assoc",
            route_table_id=self.pub_route_table.id,
            subnet_id=self.public_subnet.id,
            opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
        )

        self.additional_pub_rt_association = aws.ec2.RouteTableAssociation("kasm-additional-public-rt-assoc",
                                                                   route_table_id=self.pub_route_table.id,
                                                                   subnet_id=self.additional_public_subnet.id,
                                                                   opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
                                                                   )

        # Create a Private Route Association
        self.prv_rt_association = aws.ec2.RouteTableAssociation("kasm-private-rt-assoc",
            route_table_id=self.prv_route_table.id,
            subnet_id=self.private_subnet.id,
            opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
        )

        self.additional_prv_rt_association = aws.ec2.RouteTableAssociation("kasm-additional-private-rt-assoc",
                                                                   route_table_id=self.prv_route_table.id,
                                                                   subnet_id=self.additional_private_subnet.id,
                                                                   opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
                                                                   )

        # Enable ssh if ssh_enable is true
        sg_extra_args = {"ingress": []}
        if data.get("vm_enable_ssh"):
            sg_extra_args["ingress"] = [
                {
                    "protocol": "tcp",
                    "from_port": 22,
                    "to_port": 22,
                    "cidr_blocks": ["0.0.0.0/0"],

                }
            ]

        # Allow HTTPS and All Internal IP start with 10.0.0.0/8
        sg_extra_args["ingress"].extend(
            [{
                "protocol": -1,
                "from_port": 0,
                "to_port": 0,
                "cidr_blocks": ["10.0.0.0/8"],
            },
            {
                "protocol": "tcp",
                "from_port": 443,
                "to_port": 443,
                "cidr_blocks": ["0.0.0.0/0"],
            }
            ]
        )

        # Create a Security Group
        self.sg = aws.ec2.SecurityGroup("kasm-sg",
            egress=[
                {
                    "protocol": "-1",
                    "from_port": 0,
                    "to_port": 0,
                    "cidr_blocks": ["0.0.0.0/0"],
                }
            ],
            vpc_id=self.vpc.id,
            tags={
                  "Name": "kasm-sg",
            },
            opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider),
            **sg_extra_args
        )

        ## Create a DB Subnet Group for RDS
        self.rds_subnet_group = aws.rds.SubnetGroup("kasm-rds-subnet-group",
                                               name= "kasm-rds-subnet-group",
                                               subnet_ids= [
                                                   self.private_subnet.id,
                                                   self.additional_private_subnet.id,
                                               ],
                                                opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))


        # Create private 53 dns zone for db
        self.kasm_private_zone = aws.route53.Zone("kasm-private-zone",
                                                  name="kasm.int",
                                                  vpcs=[{
                                                      "vpc_id": self.vpc.id,
                                                  }],
                                                  opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
                                                  )

        # Create cert
        self.kasm_primary_zone_cert = aws.acm.Certificate("cert",
                                   domain_name = data.get("domain"),
                                   validation_method = "DNS",
                                   subject_alternative_names = [f'*.{data.get("domain")}'],
                                   opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
                                   )

        # Valid cert by adding DNS record
        self.kasm_primary_zone_cert_validation = aws.route53.Record("kasm-primary-zone-cert-validation",
                                                                          zone_id=public_route_53_zone.zone_id,
                                                                          name=self.kasm_primary_zone_cert.domain_validation_options[0].resource_record_name,
                                                                          type=aws.route53.RecordType.CNAME,
                                                                          ttl=300,
                                                                          records=[self.kasm_primary_zone_cert.domain_validation_options[0].resource_record_value])

        additional_zones = data.get("additional_kasm_zone") or []
        self.additional_zone_resources = {}
        # Create resources for additional Kasm zones
        for zone_index in range(2, len(data.get("additional_kasm_zone") or [])+2):
            zone_config = additional_zones[zone_index-2]
            self.additional_zone_resources[zone_config["name"]] = {}
            provider = aws.Provider(f"kasm-{zone_config['name']}-provider", region=zone_config["region"])
            self.additional_zone_resources[zone_config["name"]]["provider"] = provider

            # Create a VPC
            vpc = aws.ec2.Vpc(
                f"kasm-{zone_config['name']}-vpc",
                cidr_block=f"10.{zone_index-1}.0.0/16",
                enable_dns_hostnames=True,
                enable_dns_support=True,
                tags={
                    "Name": f"kasm-{zone_config['name']}-vpc",
                },
                opts=pulumi.ResourceOptions(provider=provider)
            )

            self.additional_zone_resources[zone_config["name"]]["vpc"] = vpc


            # Create a Private Subnet
            private_subnet = aws.ec2.Subnet(f"kasm-{zone_config['name']}-private-subnet",
                                                 vpc_id=vpc.id,
                                                 cidr_block=f"10.{zone_index-1}.0.0/24",
                                                 availability_zone = zone_config["availability_zone"],
                                                 map_public_ip_on_launch=False,
                                                 tags={
                                                     "Name": f"kasm-{zone_config['name']}-private-subnet",
                                                 },
                                                 opts=pulumi.ResourceOptions(provider=provider))

            self.additional_zone_resources[zone_config["name"]]["private_subnet"] = private_subnet

            # Create a Public Subnet
            public_subnet = aws.ec2.Subnet(f"kasm-{zone_config['name']}-public-subnet",
                                                vpc_id=vpc.id,
                                                cidr_block=f"10.{zone_index-1}.2.0/24",
                                                availability_zone = zone_config["availability_zone"],
                                                map_public_ip_on_launch=True,
                                                tags={
                                                    "Name": f"kasm-{zone_config['name']}-public-subnet",
                                                },
                                                opts=pulumi.ResourceOptions(provider=provider))

            additional_public_subnet = aws.ec2.Subnet(f"kasm-{zone_config['name']}-additional-public-subnet",
                                                           vpc_id=vpc.id,
                                                           cidr_block=f"10.{zone_index-1}.3.0/24",
                                                           availability_zone = zone_config["additional_availability_zone"],
                                                           map_public_ip_on_launch=True,
                                                           tags={
                                                               "Name": f"kasm-{zone_config['name']}-additional-public-subnet",
                                                           },
                                                           opts=pulumi.ResourceOptions(provider=provider))


            self.additional_zone_resources[zone_config["name"]]["public_subnet"] = public_subnet
            self.additional_zone_resources[zone_config["name"]]["additional_public_subnet"] = additional_public_subnet

            # Create an Elastic IP
            eip = aws.ec2.Eip(f"kasm-{zone_config['name']}-nat-eip",
                                   domain="vpc",
                                   opts=pulumi.ResourceOptions(provider=provider))
            additional_eip = aws.ec2.Eip(f"kasm-{zone_config['name']}-additional-nat-eip",
                                              domain="vpc",
                                              opts=pulumi.ResourceOptions(provider=provider))
            self.additional_zone_resources[zone_config["name"]]["eip"] = eip
            self.additional_zone_resources[zone_config["name"]]["additional_eip"] = additional_eip

            # Create an Internet Gateway
            igw = aws.ec2.InternetGateway(f"kasm-{zone_config['name']}-igw",
                                               vpc_id=vpc.id,
                                               tags={
                                                   "Name": f"kasm-{zone_config['name']}-igw",
                                               },
                                               opts=pulumi.ResourceOptions(provider=provider))
            self.additional_zone_resources[zone_config["name"]]["igw"] = igw

            # Create a NatGateway
            nat_gateway = aws.ec2.NatGateway(f"kasm-{zone_config['name']}-natgw",
                                                  allocation_id=eip.allocation_id,
                                                  subnet_id=public_subnet.id,
                                                  tags={
                                                      "Name": f"kasm-{zone_config['name']}-natgw",
                                                  },
                                                  opts=pulumi.ResourceOptions(provider=provider,
                                                                              depends_on=[igw]))
            additional_nat_gateway = aws.ec2.NatGateway(f"kasm-{zone_config['name']}-additional-natgw",
                                                             allocation_id=additional_eip.allocation_id,
                                                             subnet_id=additional_public_subnet.id,
                                                             tags={
                                                                 "Name": f"kasm-{zone_config['name']}-additional-natgw",
                                                             },
                                                             opts=pulumi.ResourceOptions(provider=provider,
                                                                                         depends_on=[igw]))
            self.additional_zone_resources[zone_config["name"]]["nat_gateway"] = nat_gateway
            self.additional_zone_resources[zone_config["name"]]["additional_nat_gateway"] = additional_nat_gateway


            # Create a Public Route Table
            pub_route_table = aws.ec2.RouteTable(f"kasm-{zone_config['name']}-public-rt",
                                                      vpc_id=vpc.id,
                                                      routes=[
                                                          aws.ec2.RouteTableRouteArgs(
                                                              cidr_block="0.0.0.0/0",
                                                              gateway_id=igw.id,
                                                          )
                                                      ],
                                                      tags={
                                                          "Name": f"kasm-{zone_config['name']}-public-rt",
                                                      },
                                                      opts=pulumi.ResourceOptions(provider=provider))

            self.additional_zone_resources[zone_config["name"]]["pub_route_table"] = pub_route_table


            # Create a private Route Table
            prv_route_table = aws.ec2.RouteTable(f"kasm-{zone_config['name']}-private-rt",
                                                      vpc_id=vpc.id,
                                                      routes=[
                                                          aws.ec2.RouteTableRouteArgs(
                                                              cidr_block="0.0.0.0/0",
                                                              gateway_id=nat_gateway.id,
                                                          )
                                                      ],
                                                      tags={
                                                          "Name": f"kasm-{zone_config['name']}-private-rt",
                                                      },
                                                      opts=pulumi.ResourceOptions(provider=provider,
                                                                                  ignore_changes=["routes"]))
            self.additional_zone_resources[zone_config["name"]]["prv_route_table"] = prv_route_table

            # Create a Public Route Association
            pub_rt_association = aws.ec2.RouteTableAssociation(f"kasm-{zone_config['name']}-public-rt-assoc",
                                                                       route_table_id=pub_route_table.id,
                                                                       subnet_id=public_subnet.id,
                                                                       opts=pulumi.ResourceOptions(provider=provider)
                                                                       )

            additional_pub_rt_association = aws.ec2.RouteTableAssociation(f"kasm-{zone_config['name']}-additional-public-rt-assoc",
                                                                               route_table_id=pub_route_table.id,
                                                                               subnet_id=additional_public_subnet.id,
                                                                               opts=pulumi.ResourceOptions(provider=provider)
                                                                               )

            self.additional_zone_resources[zone_config["name"]]["pub_route_association"] = pub_rt_association
            self.additional_zone_resources[zone_config["name"]]["additional_pub_rt_association"] = additional_pub_rt_association

            # Create a Private Route Association
            prv_rt_association = aws.ec2.RouteTableAssociation(f"kasm-{zone_config['name']}-private-rt-assoc",
                                                                       route_table_id=prv_route_table.id,
                                                                       subnet_id=private_subnet.id,
                                                                       opts=pulumi.ResourceOptions(provider=provider)
                                                                       )
            self.additional_zone_resources[zone_config["name"]]["prv_route_association"] = prv_rt_association

            # Create a Security Group
            sg = aws.ec2.SecurityGroup(f"kasm-{zone_config['name']}-sg",
                                            egress=[
                                                {
                                                    "protocol": "-1",
                                                    "from_port": 0,
                                                    "to_port": 0,
                                                    "cidr_blocks": ["0.0.0.0/0"],
                                                }
                                            ],
                                            vpc_id=vpc.id,
                                            tags={
                                                "Name": f"kasm-{zone_config['name']}-sg",
                                            },
                                            opts=pulumi.ResourceOptions(provider=provider),
                                            **sg_extra_args
                                            )
            self.additional_zone_resources[zone_config["name"]]["sg"] = sg

            # Create a VPC Peering Connection (From Primary to the additional zone)
            vpc_peering = aws.ec2.VpcPeeringConnection(f"kasm-{zone_config['name']}-vpc-peering",
                                               peer_region=data.get("region"),
                                               peer_vpc_id=self.vpc.id,
                                               vpc_id=vpc.id,
                                               tags={
                                                   "Name": f"kasm-{zone_config['name']}-vpc-peering",
                                               },
                                               opts=pulumi.ResourceOptions(provider=provider))

            self.additional_zone_resources[zone_config["name"]]["vpc_peering"] = vpc_peering

            # Accept the VPC Peering Connection
            vpc_peering_accepter = aws.ec2.VpcPeeringConnectionAccepter(
                    f"kasm-{zone_config['name']}-vpc-peering-accepter",
                    vpc_peering_connection_id=vpc_peering.id,
                    auto_accept=True,
                    tags={
                        "Name": f"kasm-{zone_config['name']}-vpc-peering-accepter",
                    },
                    opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider),
                )

            self.additional_zone_resources[zone_config["name"]]["vpc_peering_accepter"] = vpc_peering_accepter

            # Create route from primary to additional zone
            to_additional_zone_vpc_peering_prv_route = aws.ec2.Route(
                f"kasm-primary-to-{zone_config['name']}-vpc-peering-prv-route",
                route_table_id=self.prv_route_table.id,
                destination_cidr_block=vpc.cidr_block,
                vpc_peering_connection_id=vpc_peering.id,
                opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
            )

            to_additional_zone_vpc_peering_pub_route = aws.ec2.Route(
                f"kasm-primary-to-{zone_config['name']}-vpc-peering-pub-route",
                route_table_id=self.pub_route_table.id,
                destination_cidr_block=vpc.cidr_block,
                vpc_peering_connection_id=vpc_peering.id,
                opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
            )

            self.additional_zone_resources[zone_config["name"]]["to_additional_zone_vpc_peering_prv_route"] = to_additional_zone_vpc_peering_prv_route
            self.additional_zone_resources[zone_config["name"]]["to_additional_zone_vpc_peering_pub_route"] = to_additional_zone_vpc_peering_pub_route

        # self.additional_zone_resources[zone_config["name"]]["to_additional_zone_vpc_peering_pub_route"] = to_additional_zone_vpc_peering_pub_route

            # Create route from additional zone to primary zone
            to_primary_zone_vpc_peering_prv_route = aws.ec2.Route(
                    f"kasm-{zone_config['name']}-to-primary-vpc-peering-prv-route",
                    route_table_id=prv_route_table.id,
                    destination_cidr_block=self.vpc.cidr_block,
                    vpc_peering_connection_id=vpc_peering.id,
                    opts=pulumi.ResourceOptions(provider=provider)
                )

            self.additional_zone_resources[zone_config["name"]]["to_primary_zone_vpc_peering_prv_route"] = to_primary_zone_vpc_peering_prv_route

            # Create a certificate for additional zone, no seperate validation required as primary zone already added verification record
            cert = aws.acm.Certificate(f"kasm-{zone_config['name']}-cert",
                                                              domain_name = data.get("domain"),
                                                              validation_method = "DNS",
                                                              subject_alternative_names = [f'*.{data.get("domain")}'],
                                                              opts=pulumi.ResourceOptions(provider=provider)
                                                              )

            self.additional_zone_resources[zone_config["name"]]["cert"] = cert