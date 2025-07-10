import pulumi_aws as aws
from resources.aws_networking import SetupAwsNetwork
from resources.aws_db import SetupAwsDb
from resources.aws_eks import SetupEks
from pulumi import Config
import pulumi
from resources.aws_deployment import  KasmDeployment
from resources.kasm_agent import  SetupKasmAgent
from resources.kasm_config import  KasmConfig
from utils.password_generator import Password
from utils.ssh_key_generator import SSHKey
from utils.startup_script import get_agent_startup_script, get_proxy_startup_script, get_kasm_config_script, get_kasm_config_configmap


# Get stack config and aws provider
config = Config()
data = config.require_object("data")
kasm_primary_zone_aws_provider = aws.Provider("kasm-primary-zone-aws-provider", region=data.get("region"))

# Get the user defined route 53 zone
public_route_53_zone = aws.route53.get_zone(zone_id = data.get("aws_route_53_zone_id"))

# Setup AWS Network
aws_network = SetupAwsNetwork(kasm_primary_zone_aws_provider, public_route_53_zone)

# Generate DB Password and SSH Key
password = Password()
ssh_key = SSHKey()

# Setup RDS Postgres DB
aws_db = SetupAwsDb(kasm_primary_zone_aws_provider, aws_network, password.dbPassword)

# Setup EKS Cluster
eks = SetupEks(kasm_primary_zone_aws_provider, aws_network)

# Deploy Kasm Helm Chart
kasm_helm = KasmDeployment(kasm_primary_zone_aws_provider, public_route_53_zone, aws_network, aws_db, eks)

# Deploy Kasm Agent VMs
kasm_agent = SetupKasmAgent(kasm_primary_zone_aws_provider, public_route_53_zone, aws_network, kasm_helm, get_agent_startup_script, get_proxy_startup_script, ssh_key)

# Auto config Kasm
kasm_config = KasmConfig(kasm_primary_zone_aws_provider, aws_network, eks, kasm_helm, kasm_agent, ssh_key, get_kasm_config_script, get_kasm_config_configmap)

