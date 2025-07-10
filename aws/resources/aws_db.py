import pulumi
from pulumi import Config, ResourceOptions
import pulumi_aws as aws


config = Config()
data = config.require_object("data")


class SetupAwsDb:
    def __init__(self, kasm_primary_zone_aws_provider, aws_network, db_password):
        # Create DB Parameter Group
        self.db_parameter_group = aws.rds.ParameterGroup("kasm-db-parameter-group",
                                                         name = "kasm-db-parameter-group",
                                                         family = "postgres14",
                                                         parameters = [aws.rds.ParameterGroupParameterArgs(
                                                             name = "max_connections",
                                                             value = "1000",
                                                             apply_method="pending-reboot"
                                                         )],
                                                         opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider)
                                                         )

        # Create DB instance, DB and user credentials
        self.kasm_db = aws.rds.Instance("kasm-db-instance",
                                            db_name = "kasm",
                                            engine = "postgres",
                                            engine_version = "14",
                                            allocated_storage = 10,
                                            max_allocated_storage = 100,
                                            instance_class = data.get("db_instance_class"),
                                            db_subnet_group_name = aws_network.rds_subnet_group,
                                            vpc_security_group_ids = [aws_network.sg.id],
                                            auto_minor_version_upgrade = False,
                                            skip_final_snapshot = True,
                                            username = "kasmapp",
                                            password = db_password,
                                            parameter_group_name = self.db_parameter_group.name,
                                            opts=ResourceOptions(
                                                provider=kasm_primary_zone_aws_provider,
                                                depends_on=[],
                                                ignore_changes=["password"]),
                                            )

        pulumi.export("kasm_db_name", "kasm")
        pulumi.export("kasm_db_user", "kasmapp")
        pulumi.export("kasm_db_user_password", self.kasm_db.password)

        # Create DB record
        self.db_record = aws.route53.Record("kasm_private_zone",
                                            zone_id=aws_network.kasm_private_zone.id,
                                            name="db.kasm.int",
                                            type=aws.route53.RecordType.CNAME,
                                            ttl=300,
                                            records=[self.kasm_db.address],
                                            opts=pulumi.ResourceOptions(provider=kasm_primary_zone_aws_provider))

