from pulumi import Config, ResourceOptions
import pulumi_gcp as gcp
import pulumi


config = Config()
data = config.require_object("data")
gcp_config = Config("gcp")


class EnableGCPAPIs:
    def __init__(self):
        self.gcp_serviceusage_api = gcp.projects.Service("gcp_serviceusage_api",
                                                         service="serviceusage.googleapis.com",
                                                         project= gcp_config.get("project"),
                                                         disable_on_destroy=False)

        self.gcp_compute_api = gcp.projects.Service("gcp_compute_api",
                                       service="compute.googleapis.com",
                                       project= gcp_config.get("project"),
                                       disable_on_destroy=False,
                                       opts=ResourceOptions(
                                            depends_on=[self.gcp_serviceusage_api]
                                        ))

        self.gcp_container_api = gcp.projects.Service("gcp_container_api",
                                                    service="container.googleapis.com",
                                                    project= gcp_config.get("project"),
                                                    disable_on_destroy=False,
                                                    opts=ResourceOptions(
                                                         depends_on=[self.gcp_serviceusage_api]
                                                      ))

        self.gcp_dns_api = gcp.projects.Service("gcp_dns_api",
                                                    service="dns.googleapis.com",
                                                    project= gcp_config.get("project"),
                                                    disable_on_destroy=False,
                                                    opts=ResourceOptions(
                                                         depends_on=[self.gcp_serviceusage_api]
                                                    ))

        self.gcp_servicenetworking_api = gcp.projects.Service("gcp_servicenetworking_api",
                                                    service="servicenetworking.googleapis.com",
                                                    project= gcp_config.get("project"),
                                                    disable_on_destroy=False,
                                                    opts=ResourceOptions(
                                                         depends_on=[self.gcp_serviceusage_api]
                                                              ))

        self.gcp_sqladmin_api = gcp.projects.Service("gcp_sqladmin_api",
                                                    service="sqladmin.googleapis.com",
                                                    project= gcp_config.get("project"),
                                                    disable_on_destroy=False,
                                                    opts=ResourceOptions(
                                                         depends_on=[self.gcp_serviceusage_api]
                                                     ))

        self.gcp_certificatemanager_api = gcp.projects.Service("gcp_certificatemanager_api",
                                                               service="certificatemanager.googleapis.com",
                                                               disable_on_destroy=False,
                                                               opts=pulumi.ResourceOptions(
                                                                   depends_on=[self.gcp_serviceusage_api]
                                                               ))

