from pulumi import Config
from pulumi_kubernetes.helm.v3 import Release, ReleaseArgs
from pulumi_kubernetes.core.v1 import Secret
from pulumi_kubernetes.networking.v1 import Ingress
import pulumi_aws as aws
import pulumi
import base64
from time import sleep

config = Config()
data = config.require_object("data")
gcp_config = Config("gcp")
secrets = config.require_secret_object("data")
additional_zone = data.get("additional_kasm_zone") or []


class KasmDeployment:
    def __init__(self, kasm_primary_zone_aws_provider, public_route_53_zone, aws_network, aws_db, eks):
        # Load the zone configuration
        helm_zone_config = []
        alt_hostname = [f'*.{data.get("domain")}']
        for zone_index in range(len(additional_zone)):
            zone_name = additional_zone[zone_index]["name"]
            zone_config = {
                "name": zone_name,
                "cloudProvider": "aws",
                "hostName": additional_zone[zone_index]["domain"],
                "certificateArn": aws_network.kasm_primary_zone_cert.arn
            }
            helm_zone_config.append(zone_config)
            alt_hostname.append(additional_zone[zone_index]["domain"])
            alt_hostname.append(additional_zone[zone_index]["proxy_domain"])

        # Deploying Helm
        self.helm = Release("kasm-helm",
                            ReleaseArgs(
                                chart="./kasm-helm/kasm-pulumi",
                                values={
                                    "global": {
                                        "hostname": data.get("domain"),
                                        "altHostnames": alt_hostname,
                                        "pulumiDeployment": {
                                            "cloudProvider": "aws",
                                            "certificateArn": aws_network.kasm_primary_zone_cert.arn,
                                            "additionalZone": helm_zone_config
                                        },
                                        "standAloneDb": {
                                            "postgresHost": "db.kasm.int"
                                        },
                                        "kasmPasswords": {
                                            "dbPassword": aws_db.kasm_db.password,
                                        },
                                    },
                                },
                                namespace="kasm",
                                skip_await=False,
                                create_namespace=True,
                                timeout=1800
                            ),
                            opts=pulumi.ResourceOptions(
                                provider=eks.k8s_provider,
                                depends_on=[aws_db.kasm_db, eks.kasm_cluster, eks.k8s_provider]
                            )
                            )

        # Get the Created Secrets
        self.kasm_secrets = Secret.get(f'kasm/kasm-secrets',
                                       self.helm.status.status.apply(lambda v: f'kasm/kasm-secrets'),
                                       opts=pulumi.ResourceOptions(
                                           depends_on=[self.helm],
                                           provider=eks.k8s_provider,
                                       )
                                       )

        self.kasm_ingress = Ingress.get("kasm-ingress",
                                        self.helm.status.status.apply(lambda v: f'kasm/kasm-ingress'),
                                        opts=pulumi.ResourceOptions(
                                            depends_on=[self.helm],
                                            provider=eks.k8s_provider,
                                        )
        )

        self.elb_hosted_zone_id = aws.elb.get_hosted_zone_id(data.get("region")).id

        self.kasm_primary_zone_record = aws.route53.Record("kasm-primary-zone-record",
                                                           zone_id=public_route_53_zone.zone_id,
                                                           name=data.get("domain"),
                                                           type=aws.route53.RecordType.A,
                                                           aliases=[{
                                                               "name": self.kasm_ingress.status.apply(lambda status: status.load_balancer.ingress[0].hostname),
                                                               "zone_id": self.elb_hosted_zone_id,
                                                               "evaluate_target_health": True,
                                                           }],
                                                           opts=pulumi.ResourceOptions(
                                                               depends_on=[self.helm, self.kasm_ingress],
                                                           ))

        additional_zones = data.get("additional_kasm_zone") or []
        self.kasm_additional_zone_ingress = []
        self.kasm_additional_zone_record = []
        for zone_index in range(2, len(data.get("additional_kasm_zone") or [])+2):
            zone_config = additional_zones[zone_index-2]
            zone_name = zone_config["name"]
            zone_domain = zone_config["domain"]
            kasm_ingress = Ingress.get(f"kasm-{zone_name}-ingress",
                                            self.helm.status.status.apply(lambda v, z=zone_name: f"kasm/kasm-{z}-ingress"),
                                            opts=pulumi.ResourceOptions(
                                                depends_on=[self.helm],
                                                provider=eks.k8s_provider,
                                            )
                                            )
            self.kasm_additional_zone_ingress.append(kasm_ingress)

            kasm_additional_zone_record = aws.route53.Record(f"kasm-{zone_name}-zone-record",
                                                               zone_id=public_route_53_zone.zone_id,
                                                               name=zone_domain,
                                                               type=aws.route53.RecordType.A,
                                                               aliases=[{
                                                                   "name": kasm_ingress.status.apply(lambda status: status.load_balancer.ingress[0].hostname),
                                                                   "zone_id": self.elb_hosted_zone_id,
                                                                   "evaluate_target_health": True,
                                                               }],
                                                               opts=pulumi.ResourceOptions(
                                                                   depends_on=[self.helm, kasm_ingress],
                                                               ))
            self.kasm_additional_zone_record.append(kasm_additional_zone_record)


        # Get the Created SSL Cert Secret
        self.kasm_ingress_cert = Secret.get(f'kasm/kasm-ingress-cert',
                                            self.helm.status.status.apply(lambda v: f'kasm/kasm-ingress-cert'),
                                            opts=pulumi.ResourceOptions(
                                                depends_on=[self.helm],
                                                provider=eks.k8s_provider,
                                            )
                                            )
        self.kasm_nginx_proxy_cert = Secret.get(f'kasm/kasm-nginx-proxy-cert',
                                                self.helm.status.status.apply(lambda v: f'kasm/kasm-nginx-proxy-cert'),
                                                opts=pulumi.ResourceOptions(
                                                    depends_on=[self.helm],
                                                    provider=eks.k8s_provider,
                                                )
                                                )

        # Exporting Secrets
        self.manager_token = self.kasm_secrets.data["manager-token"].apply(lambda v: base64.b64decode(v).decode('utf-8'))
        self.service_token = self.kasm_secrets.data["service-token"].apply(lambda v: base64.b64decode(v).decode('utf-8'))
        self.tls_crt = self.kasm_ingress_cert.data["tls.crt"].apply(lambda v: base64.b64decode(v).decode('utf-8'))
        self.tls_key = self.kasm_ingress_cert.data["tls.key"].apply(lambda v: base64.b64decode(v).decode('utf-8'))
        self.nginx_tls_crt = self.kasm_nginx_proxy_cert.data["tls.crt"].apply(lambda v: base64.b64decode(v).decode('utf-8'))
        self.nginx_tls_key = self.kasm_nginx_proxy_cert.data["tls.key"].apply(lambda v: base64.b64decode(v).decode('utf-8'))
        self.admin_pass = self.kasm_secrets.data["admin-password"].apply(lambda v: base64.b64decode(v).decode('utf-8'))
        pulumi.export("Kasm URL", data.get("domain"))
        pulumi.export("Kasm Admin User:", "admin@kasm.local")
        pulumi.export("Kasm Un-privileged User", "user@kasm.local")
        pulumi.export("Kasm Admin Password", self.admin_pass)
        pulumi.export("Kasm Manager Token", self.manager_token)
        pulumi.export("Kasm Service Registration Token", self.service_token)
        pulumi.export("Kasm Redis Password", self.kasm_secrets.data["redis-password"].apply(lambda v: base64.b64decode(v).decode('utf-8')))