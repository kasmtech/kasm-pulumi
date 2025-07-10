from resources.gcp_api import EnableGCPAPIs
from resources.gcp_networking import SetupGcpNetwork
from resources.gcp_db import SetupGcpDb
from resources.gcp_kubernetes import SetupGcpKubernetes
from resources.kasm_deployment import KasmDeployment
from resources.kasm_agent import SetupKasmAgent
from resources.kasm_config import KasmConfig
from utils.password_generator import password_generator
from utils.startup_script import get_agent_startup_script, get_proxy_startup_script, get_kasm_config_script, get_kasm_config_configmap
from pulumi import Config

config = Config()
data = config.require_object("data")

# if auto_enable_gcp_api is configured to true
if data.get("auto_enable_gcp_api"):
    # Enable the needed GCP APIs
    gcp_api = EnableGCPAPIs()
    # Setup GCP Network
    gcp_network = SetupGcpNetwork(gcp_api)

else:
    gcp_network = SetupGcpNetwork(None)

# Create GCP postgres DB
db_password = password_generator(13)
gcp_db = SetupGcpDb(gcp_network, db_password)

# Crete GKE Cluster
gcp_cluster = SetupGcpKubernetes(gcp_network)

# Deploy Kasm Helm
kasm_helm = KasmDeployment(gcp_network, gcp_cluster, gcp_db)

# Deploy Kasm Agents
kasm_agent = SetupKasmAgent(gcp_network, kasm_helm, get_agent_startup_script, get_proxy_startup_script)

# Config Kasm
kasm_config = KasmConfig(gcp_cluster, kasm_helm, kasm_agent, get_kasm_config_script, get_kasm_config_configmap, gcp_network)