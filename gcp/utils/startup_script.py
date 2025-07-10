import pulumi

def get_agent_startup_script(agent_swap_size, kasm_build_url, manager_url, manager_token):

    return pulumi.Output.all(agent_swap_size,
                             kasm_build_url,
                             manager_url,
                             manager_token
                             ).apply(lambda v: f"""#!/bin/bash
set -ex
echo "Starting Kasm Workspaces Agent Install"

## Create Swap partition
fallocate -l "{v[0]}"g /var/kasm.swap
chmod 600 /var/kasm.swap
mkswap /var/kasm.swap
swapon /var/kasm.swap
echo '/var/kasm.swap swap swap defaults 0 0' | tee -a /etc/fstab

cd /tmp

PRIVATE_IP=(`hostname -I | cut -d' ' -f1 | tr -d '\\n'`)

wget  {v[1]} -O kasm_workspaces.tar.gz
tar -xf kasm_workspaces.tar.gz

echo "Waiting for Kasm WebApp availability..."
while ! (curl -k https://{v[2]}/api/__healthcheck 2>/dev/null | grep -q true)
do
  echo "Waiting for API server..."
  sleep 5
done
echo "WebApp is alive"

bash kasm_release/install.sh -S agent -e -H -p $PRIVATE_IP -m {v[2]} -M {v[3]}

echo "Done"
"""
                                     )

def get_proxy_startup_script(domain, service_token, zone, cert, cert_key):

    return pulumi.Output.all(domain, service_token, zone, cert, cert_key).apply(lambda v: f"""#!/bin/bash
# If the directory does not exist, clone the repository
cd /tmp

if [ ! -d "/tmp/kasm-pulumi" ]; then
    git clone https://github.com/kasmtech/kasm-pulumi.git
fi

sudo mkdir -p /tmp/kasm-pulumi/additional_zone/dedicated_proxy/kasm-docker-compose/certs
sudo cat > /tmp/kasm-pulumi/additional_zone/dedicated_proxy/kasm-docker-compose/certs/server.crt << EOL
{v[3]}
EOL

sudo cat > /tmp/kasm-pulumi/additional_zone/dedicated_proxy/kasm-docker-compose/certs/server.key << EOL
{v[4]}
EOL

echo "Waiting for Kasm WebApp availability..."
while ! (curl -k "https://{v[0]}/api/__healthcheck" 2>/dev/null | grep -q "true"); do
    echo "Waiting for API server at {v[0]}..."
    sleep 5
done
echo "WebApp is alive"


# setting up the proxy
bash /tmp/kasm-pulumi/additional_zone/dedicated_proxy/install.sh --domain "{v[0]}" --service-token "{v[1]}" --zone "{v[2]}" --cert "/tmp/kasm-pulumi/additional_zone/dedicated_proxy/kasm-docker-compose/certs/server.crt" --cert-key "/tmp/kasm-pulumi/additional_zone/dedicated_proxy/kasm-docker-compose/certs/server.key" 

"""
                                     )

def get_kasm_config_script():
    return """apt-get update -y;
apt-get install curl jq -y;
cp /tmp/kasm_config.sh ./;
chmod +x kasm_config.sh;
./kasm_config.sh;
"""

def get_kasm_config_configmap():
    f = open("utils/kasm_config.sh", "r")
    return f.read()