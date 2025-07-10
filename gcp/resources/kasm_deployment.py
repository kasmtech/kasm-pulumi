from pulumi import Config
from pulumi_kubernetes.helm.v3 import Release, ReleaseArgs
from pulumi_kubernetes.core.v1 import Secret
from pulumi_kubernetes.networking.v1 import Ingress

import pulumi_kubernetes as k8s
import pulumi
import base64
from time import sleep

config = Config()
data = config.require_object("data")
gcp_config = Config("gcp")
secrets = config.require_secret_object("data")
additional_zone = data.get("additional_kasm_zone") or []

class KasmDeployment:
    def __init__(self, gcp_network, gcp_cluster, gcp_db):
        # Load the zone configuration
        helm_zone_config = []
        alt_hostname = [f'*.{data.get("domain")}']
        for zone_index in range(len(additional_zone)):
            zone_config = {
                "name": additional_zone[zone_index]["name"],
                "cloudProvider": "gcp",
                "hostName": additional_zone[zone_index]["domain"],
                "loadBalancerIP": gcp_network.additional_zone_public_ip_address[zone_index].name
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
                                       "cloudProvider": "gcp",
                                       "loadBalancerIP": gcp_network.public_ip_address.name,
                                       "additionalZone": helm_zone_config,
                                       "cert": gcp_network.kasm_cert.name
                                   },
                                   "standAloneDb": {
                                       "postgresHost": "db.kasm.int"
                                   },
                                   "kasmPasswords": {
                                       "dbPassword": gcp_db.kasm_user.password,
                                   },
                               },
                           },
                           namespace="kasm",
                           skip_await=False,
                           create_namespace=True,
                           timeout=1800
                       ),
                       opts=pulumi.ResourceOptions(
                           provider=gcp_cluster.cluster_provider,
                           depends_on=[gcp_db.kasm_user, gcp_db.kasm_db, gcp_cluster.cluster, gcp_cluster.cluster_provider, gcp_network.kasm_cert]
                       )
                       )

        # Get the Created Secrets
        self.kasm_secrets = Secret.get(f'kasm/kasm-secrets',
                                       self.helm.status.status.apply(lambda v: f'kasm/kasm-secrets'),
                                                    opts=pulumi.ResourceOptions(
                                                        depends_on=[self.helm],
                                                        provider=gcp_cluster.cluster_provider,
                                                    )
                                                    )

        # Get the Created SSL Cert Secret
        self.kasm_ingress_cert = Secret.get(f'kasm/kasm-ingress-cert',
                                       self.helm.status.status.apply(lambda v: f'kasm/kasm-ingress-cert'),
                                       opts=pulumi.ResourceOptions(
                                           depends_on=[self.helm],
                                           provider=gcp_cluster.cluster_provider,
                                       )
                                       )
        self.kasm_nginx_proxy_cert = Secret.get(f'kasm/kasm-nginx-proxy-cert',
                                            self.helm.status.status.apply(lambda v: f'kasm/kasm-nginx-proxy-cert'),
                                            opts=pulumi.ResourceOptions(
                                                depends_on=[self.helm],
                                                provider=gcp_cluster.cluster_provider,
                                            )
                                            )

        # self.ingress = Ingress.get(f'kasm/kasm-ingress',
        #                                         self.helm.status.status.apply(lambda v: f'kasm/kasm-ingress'),
        #                                         opts=pulumi.ResourceOptions(
        #                                             depends_on=[self.helm],
        #                                             provider=gcp_cluster.cluster_provider,
        #                                         )
        #                                         )
        #
        # pulumi.export("test", self.ingress)


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
