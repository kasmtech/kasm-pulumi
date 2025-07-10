import pulumi
import json
import pulumi_aws as aws
from pulumi import Config, ResourceOptions
import pulumi_eks as eks
import pulumi_kubernetes as k8s


config = Config()
data = config.require_object("data")


class SetupEks:
    def __init__(self, kasm_primary_zone_aws_provider, aws_network):
        # Create EKS cluster in auto mode
        self.kasm_cluster = eks.Cluster("kasm-eks-cluster",
                                        name = "kasm-eks-cluster",
                                        authentication_mode = eks.AuthenticationMode.API,
                                        vpc_id = aws_network.vpc.id,
                                        public_subnet_ids = [aws_network.public_subnet.id, aws_network.additional_public_subnet.id],
                                        private_subnet_ids = [aws_network.private_subnet.id, aws_network.additional_private_subnet.id],
                                        auto_mode = eks.AutoModeOptionsArgs(
                                            enabled = True,
                                        ),
                                        opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
        )

        # Create k8s provider
        self.k8s_provider = k8s.Provider("eks-k8s", kubeconfig=self.kasm_cluster.kubeconfig)
        pulumi.export("kubeconfig", pulumi.Output.secret(self.kasm_cluster.kubeconfig))

        # Adding Current AWS user (used by Pulumi) to the cluster ACL
        self.caller = aws.get_caller_identity()
        self.aws_auth = k8s.core.v1.ConfigMap(
            "aws-auth",
            metadata={"name": "aws-auth", "namespace": "kube-system"},
            data={
                "mapUsers": pulumi.Output.secret(f"""
- userarn: {self.caller.arn}
  username: {self.caller.arn.split('/')[-1]}
  groups:
    - system:masters
""")
            },
            opts=pulumi.ResourceOptions(provider=self.k8s_provider)
        )

        # Create Ingress Class that uses AWS ALB
        self.alb_ingress_class = k8s.networking.v1.IngressClass(
            "alb-ingress-class",
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name="alb",
                annotations={
                    "ingressclass.kubernetes.io/is-default-class": "true"
                }
            ),
            spec=k8s.networking.v1.IngressClassSpecArgs(
                controller="eks.amazonaws.com/alb",
                parameters=k8s.networking.v1.IngressClassParametersReferenceArgs(
                    api_group="eks.amazonaws.com",
                    kind="IngressClassParams",
                    name="alb"
                )
            ),
            opts=pulumi.ResourceOptions(provider=self.k8s_provider)
        )

        # Create Ingress Class Param
        self.alb_ingress_class_params = k8s.apiextensions.CustomResource(
            "alb-ingress-class-params",
            api_version="eks.amazonaws.com/v1",
            kind="IngressClassParams",
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name="alb"
            ),
            spec={
                "scheme": "internet-facing"
            },
            opts=pulumi.ResourceOptions(provider=self.k8s_provider)
        )

        # Create Storage Class that uses EBS
        self.storage_class = k8s.storage.v1.StorageClass(
            "auto-ebs-sc",
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name="auto-ebs-sc",
                annotations={
                    "storageclass.kubernetes.io/is-default-class": "true"
                }
            ),
            provisioner="ebs.csi.eks.amazonaws.com",
            volume_binding_mode="WaitForFirstConsumer",
            parameters={
                "type": "gp3",
                "encrypted": "true"
            },
            opts=pulumi.ResourceOptions(provider=self.k8s_provider)
        )



