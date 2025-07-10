from pulumi import Config, ResourceOptions, Output, CustomTimeouts
from pulumi_gcp.container import Cluster, ClusterReleaseChannelArgs, ClusterPrivateClusterConfigArgs, \
    ClusterIpAllocationPolicyArgs, ClusterDnsConfigArgs
from pulumi_kubernetes import Provider
import pulumi

config = Config()
data = config.require_object("data")
gcp_config = Config("gcp")


class SetupGcpKubernetes:
    def __init__(self, gcp_network):
        # Create a GKE cluster
        self.cluster = Cluster(f"kasm-cluster",
                               name=f"kasm-cluster",
                               location=data.get("region"),
                               enable_autopilot=True,
                               network=gcp_network.vpc.id,
                               subnetwork=gcp_network.subnet.id,
                               deletion_protection = False,
                               release_channel=ClusterReleaseChannelArgs(
                                   channel="STABLE"
                               ),
                               opts=ResourceOptions(
                                   depends_on=[gcp_network.private_vpc_connection],
                                   ignore_changes=["dnsConfig"])
                               )

        # Construct K8S configuration
        self.cluster_info = Output.all(self.cluster.name, self.cluster.endpoint,
                                       self.cluster.master_auth)
        self.cluster_config = self.cluster_info.apply(
            lambda info: """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {0}
    server: https://{1}
  name: {2}
contexts:
- context:
    cluster: {2}
    user: {2}
  name: {2}
current-context: {2}
kind: Config
preferences: {{}}
users:
- name: {2}
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: gke-gcloud-auth-plugin
      installHint: Install gke-gcloud-auth-plugin for use with kubectl by following
        https://cloud.google.com/blog/products/containers-kubernetes/kubectl-auth-changes-in-gke
      provideClusterInfo: true
""".format(info[2]['cluster_ca_certificate'], info[1],
           '{0}_{1}_{2}'.format(gcp_config.get("project"), data.get("zone"), info[0])))

        # Construct K8S provider
        self.cluster_provider = Provider('gke_k8s',
                                         kubeconfig=self.cluster_config,
                                         opts=ResourceOptions(depends_on=[self.cluster],
                                                              custom_timeouts=CustomTimeouts(create='30m')))