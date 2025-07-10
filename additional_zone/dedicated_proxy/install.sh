#!/bin/bash

# Exit immediately if any command fails
set -e

# Function to display usage
usage() {
    echo "Usage: $0 --domain <domain_name> --service-token <service_token> --zone <zone> --cert-key <cert_key> --cert <cert>"
    echo "  --domain        The domain name"
    echo "  --service-token The service token"
    echo "  --zone          The zone (e.g., us-east-1)"
    echo "  --cert-key      The certificate key file location"
    echo "  --cert          The certificate file location"
    exit 1
}

# Parse command-line options using getopt
TEMP=$(getopt -o '' --long domain:,service-token:,zone:,cert-key:,cert: -- "$@")
eval set -- "$TEMP"

# Default values
domain=""
service_token=""
zone=""
cert_key=""
cert=""

# Process the options
while true; do
    case "$1" in
        --domain)
            domain="$2"
            shift 2
            ;;
        --service-token)
            service_token="$2"
            shift 2
            ;;
        --zone)
            zone="$2"
            shift 2
            ;;
        --cert-key)
            cert_key="$2"
            shift 2
            ;;
        --cert)
            cert="$2"
            shift 2
            ;;
        --)
            shift
            break
            ;;
        *)
            usage
            ;;
    esac
done

# Check if all required fields are provided
if [ -z "$domain" ] || [ -z "$service_token" ] || [ -z "$zone" ] || [ -z "$cert_key" ] || [ -z "$cert" ]; then
    echo "Error: --domain, --service-token, --zone, --cert-key, and --cert are required!"
    usage
fi

if [[ ! -e /opt/kasm/proxy-startup-script-completed ]]; then
    # Add Docker's official GPG key:
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    # Add the repository to Apt sources:
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin


    cd /tmp
    if [ ! -d "/tmp/Kasm-Pulumi" ]; then
        # If the directory does not exist, clone the repository
        git clone https://github.com/chenbishop/Kasm-Pulumi.git
    fi
    sudo mkdir /opt/kasm
    sudo cp -r /tmp/Kasm-Pulumi/additional_zone/dedicated_proxy/kasm-docker-compose /opt/kasm/

    sudo cat > /opt/kasm/kasm-docker-compose/.env << EOL
KASM_API_HOSTNAME="$domain"
KASM_REGISTRATION_TOKEN="$service_token"
KASM_ZONE="$zone"
SERVER_ADDRESS="$HOSTNAME"
EOL


    sudo sed -i "s|proxy_pass https://example.example.com:443/api/kasm_connect/;|proxy_pass https://$domain:443/api/kasm_connect/;|" /opt/kasm/kasm-docker-compose/conf/nginx/services.d/upstream_proxy.conf
    sudo sed -i "s|hostnames: \[ \"example.example.com\" \]|hostnames: [ \"$domain\" ]|" /opt/kasm/kasm-docker-compose/rdpgw_kasm.yaml

    sudo mkdir -p /opt/kasm/kasm-docker-compose/certs/

    if [ ! -f /opt/kasm/kasm-docker-compose/certs/server.crt ]; then
        sudo cp "$cert" /opt/kasm/kasm-docker-compose/certs/server.crt
    fi

    if [ ! -f /opt/kasm/kasm-docker-compose/certs/server.key ]; then
        sudo cp "$cert_key" /opt/kasm/kasm-docker-compose/certs/server.key
    fi

    cd /opt/kasm/kasm-docker-compose
    sudo docker network create kasm_default_network
    sudo docker compose up -d
    sudo touch /opt/kasm/proxy-setup-completed
    echo "Proxy Startup Script Completed."
fi;