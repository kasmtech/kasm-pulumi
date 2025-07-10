while true; do
  http_status=$(curl -k -s -o /dev/null -w "%{http_code}" "https://$URL");

  if (( http_status == 200 )); then
    echo "Site is up. Proceeding with the script...";
    break;
  else
    echo "Site not reachable. HTTP Status: $http_status. Retrying in 30 seconds...";
    sleep 30;
  fi;
done;

KASM_TOKEN=$(curl -s "https://$URL/api/authenticate"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   --data-raw '{"username":"admin@kasm.local","password":"'"$ADMIN_PASS"'","token":null}' | jq -r '.token');

if [ "$KASM_TOKEN" == "null" ] || [ -z "$KASM_TOKEN" ]; then
    echo "Error: Failed to retrieve the token."
    echo "Response: $KASM_TOKEN"
    exit 2
fi

response=$(curl "https://$URL/api/admin/get_servers"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "session_token=$KASM_TOKEN"   --data-raw '{"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');

while true; do
  server_count=$(echo "$response" | jq -r '.servers | length');

  # If the server count matches AGENT_NUMBER, break the loop
  if (( server_count == AGENT_NUMBER )); then
    break;
  fi;

  echo "Waiting for the servers array size to be $AGENT_NUMBER (currently $server_count)...";
  sleep 30;

  # Re-fetch the response in case it changes
  response=$(curl "https://$URL/api/admin/get_servers"     -k     -s     -H 'accept: application/json'     -H 'content-type: application/json'     -b "session_token=$KASM_TOKEN"     --data-raw '{"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');
done;

for server_info in $(echo "$response" | jq -r '.servers[] | @base64'); do
  server_id=$(echo $server_info | base64 --decode | jq -r '.server_id')
  hostname=$(echo $server_info | base64 --decode | jq -r '.hostname')
  if [[ "$AGENT_LIST" =~ "$hostname" ]]; then
    echo "Enabling agent server with ID: $server_id and hostname: $hostname";
      curl "https://$URL/api/admin/update_server"       -k       -s       -H 'accept: application/json'       -H 'content-type: application/json'       -b "username=admin@kasm.local; session_token=$KASM_TOKEN"       --data-raw '{"target_server":{"server_type":"host","server_id":"'"$server_id"'","enabled":true},"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}'       > /dev/null 2>&1;
  else
    echo "Skipping server with with ID: $server_id and hostname: $hostname, not part of the pulumi deployment.";
  fi;
done;

response=$(curl "https://$URL/api/admin/get_zones"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "username=admin@kasm.local; session_token=$KASM_TOKEN"   --data-raw '{"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');

while true; do
  zone_count=$(echo "$response" | jq -r '.zones | length');

  if (( zone_count - 1 == ADDITIONAL_ZONES )); then
    break;
  fi;

  echo "Waiting for the zone array size to be  $((ADDITIONAL_ZONES + 1)) (currently $zone_count)...";
  sleep 5  # Wait for 5 seconds before checking again;

  # Re-fetch the response in case it changes
  response=$(curl "https://$URL/api/admin/get_zones"     -k     -s     -H 'accept: application/json'     -H 'content-type: application/json'     -b "username=admin@kasm.local; session_token=$KASM_TOKEN"     --data-raw '{"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');
done;

echo "$response" | jq -c '.zones[] | select(.zone_name != "default")' | while IFS= read -r zone; do
  zone_id=$(echo "$zone" | jq -r '.zone_id');
  zone_name=$(echo "$zone" | jq -r '.zone_name');
  eval UPSTREAM_AUTH_ADDRESS=\$$zone_name"_UPSTREAM_AUTH_ADDRESS";
  eval PROXY_HOSTNAME=\$$zone_name"_PROXY_HOSTNAME";

  echo "Updating zone with zone_id: $zone_id, zone_name: $zone_name";
  curl  "https://$URL/api/admin/update_zone"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "username=admin@kasm.local; session_token=$KASM_TOKEN"   --data-raw '{"target_zone":{"upstream_auth_address":"'"$UPSTREAM_AUTH_ADDRESS"'","proxy_hostname":"'"$PROXY_HOSTNAME"'","proxy_rdp_hostname":"'"$PROXY_HOSTNAME"'","zone_id":"'"$zone_id"'"},"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}'       > /dev/null 2>&1;
done;

echo "$response" | jq -c '.zones[] | select(.zone_name == "default")' | while IFS= read -r zone; do
  zone_id=$(echo "$zone" | jq -r '.zone_id');
  zone_name=$(echo "$zone" | jq -r '.zone_name');

  echo "Updating zone with zone_id: $zone_id, zone_name: $zone_name";
  curl  "https://$URL/api/admin/update_zone"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "username=admin@kasm.local; session_token=$KASM_TOKEN"   --data-raw '{"target_zone":{"upstream_auth_address":"'"$URL"'","zone_id":"'"$zone_id"'"},"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}'       > /dev/null 2>&1;
done;

response=$(curl "https://$URL/api/admin/get_groups"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "username=admin@kasm.local; session_token=$KASM_TOKEN"   --data-raw '{"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');
ALL_USER_GROUP_ID=$(echo "$response" | jq -r '.groups[] | select(.name == "All Users") | .group_id');

response=$(curl "https://$URL/api/admin/get_settings_group"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "username=admin@kasm.local; session_token=$KASM_TOKEN"   --data-raw '{"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');
GROUP_SETTING_ID=$(echo "$response" | jq -r '.settings[] | select(.name == "allow_zone_selection")| .group_setting_id');

echo "Adding group setting id $GROUP_SETTING_ID to group id $ALL_USER_GROUP_ID";
curl  "https://$URL/api/admin/add_settings_group"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "username=admin@kasm.local; session_token=$KASM_TOKEN"   --data-raw '{"target_group":{"group_id":"'"$ALL_USER_GROUP_ID"'"},"target_setting":{"group_setting_id":"'"$GROUP_SETTING_ID"'","value":"True"},"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}'       > /dev/null 2>&1;

echo "Creating Kasm Server Pool"
response=$(curl "https://$URL/api/admin/create_server_pool"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "username=admin@kasm.local; session_token=$KASM_TOKEN"   --data-raw '{"target_server_pool":{"server_pool_name":"gcp_autoscaler_pool","server_pool_type":"Docker Agent"},"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');       > /dev/null 2>&1;
SERVER_POOL_ID=$(echo "$response" | jq -r '.server_pool.server_pool_id');
echo "Created Server Pool with ID: $SERVER_POOL_ID"

echo "Creating Kasm Auto Scaling Config"
response=$(curl "https://$URL/api/admin/get_zones"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b "username=admin@kasm.local; session_token=$KASM_TOKEN"   --data-raw '{"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');
ZONE_INFO=$(echo "$response" | jq '{
  zones: [.zones[] | {
    zone_name: .zone_name,
    zone_id: .zone_id,
    total_memory_gb: (
      if (.servers | length) == 0 then 16 else (([.servers[].memory] | add) / 1073741824) | ceil end
    ),
    total_cores: (
      if (.servers | length) == 0 then 8 else ([.servers[].cores] | add) end
    ),
    avg_memory_gb: (
      if (.servers | length) == 0 then 16 else ((([.servers[].memory] | add) / (.servers | length) / 1073741824) | ceil) end
    ),
    avg_memory_mb: (
      if (.servers | length) == 0 then 16 * 1024 else (((([.servers[].memory] | add) / (.servers | length) / 1073741824) | ceil) * 1024) end
    ),
    avg_cores: (
      if (.servers | length) == 0 then 8 else (([.servers[].cores] | add) / (.servers | length) | ceil) end
    )
  }]
}')

CERT_ESCAPED=${CERT//$'\n'/\\n}
CERT_KEY_ESCAPED=${CERT_KEY//$'\n'/\\n}

gcp_info=$(echo "$GCP_INFO")
agent_disk_size=$(echo "$gcp_info" | jq -r '.agent_disk_size')
network=$(echo "$gcp_info" | jq -r '.network')
project=$(echo "$gcp_info" | jq -r '.project')
image=$(echo "$gcp_info" | jq -r '.image')

echo "$ZONE_INFO" | jq -c '.zones[]' | while read -r zone; do
  zone_name=$(echo "$zone" | jq -r '.zone_name')
  zone_id=$(echo "$zone" | jq -r '.zone_id')
  total_mem=$(echo "$zone" | jq -r '.total_memory_gb')
  total_cores=$(echo "$zone" | jq -r '.total_cores')
  avg_memory_gb=$(echo "$zone" | jq -r '.avg_memory_gb')
  avg_cores=$(echo "$zone" | jq -r '.avg_cores')
  avg_memory_mb=$(echo "$zone" | jq -r '.avg_memory_mb')

  if [ "$zone_name" != "default" ]; then
    zone_info=$(echo "$GCP_INFO" | jq -r --arg name "$zone_name" '.["additional_zone"][0][] | select(.name == $name)')
    subnet=$(echo "$zone_info" | jq -r '.subnet')
    max_instance=$(echo "$zone_info" | jq -r '.["max_instance"]')
    agent_size=$(echo "$zone_info" | jq -r '.agent_size')
    region=$(echo "$zone_info" | jq -r '.region')
    zone=$(echo "$zone_info" | jq -r '.zone')
  else
    subnet=$(echo "$gcp_info" | jq -r '.subnet')
    max_instance=$(echo "$gcp_info" | jq -r '.["max_instance"]')
    agent_size=$(echo "$gcp_info" | jq -r '.agent_size')
    region=$(echo "$gcp_info" | jq -r '.region')
    zone=$(echo "$gcp_info" | jq -r '.zone')
  fi

  script_body=$'#\u0021/bin/bash\\nset -ex\\n\\n# Note: Templated items (e.g \'<bracket>foo<bracket>\') will be replaced by Kasm when provisioning the system\\nGIVEN_HOSTNAME=\'{server_hostname}\'\\nGIVEN_FQDN=\'{server_external_fqdn}\'\\nMANAGER_TOKEN=\'{manager_token}\'\\n# Ensure the Upstream Auth Address in the Zone is set to an actual DNS name or IP and NOT $request_host$\\nMANAGER_ADDRESS=\'{upstream_auth_address}\'\\nSERVER_ID=\'{server_id}\'\\nPROVIDER_NAME=\'{provider_name}\'\\n# Swap size in MB, adjust appropriately depending on the size of your Agent VMs\\nSWAP_SIZE_GB=\'8\'\\nKASM_BUILD_URL=\'https://kasm-static-content.s3.amazonaws.com/kasm_release_1.17.0.bbc15c.tar.gz\'\\n\\n\\napt_wait () {{\\n  while sudo fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do\\n    sleep 1\\n  done\\n  while sudo fuser /var/lib/apt/lists/lock >/dev/null 2>&1 ; do\\n    sleep 1\\n  done\\n  if [ -f /var/log/unattended-upgrades/unattended-upgrades.log ]; then\\n    while sudo fuser /var/log/unattended-upgrades/unattended-upgrades.log >/dev/null 2>&1 ; do\\n      sleep 1\\n    done\\n  fi\\n}}\\n\\n\\n# Create a swap file\\nif [[ $(sudo swapon --show) ]]; then\\n  echo \'Swap Exists\'\\nelse\\n  fallocate -l ${{SWAP_SIZE_GB}}G /var/swap.1\\n  /sbin/mkswap /var/swap.1\\n  chmod 600 /var/swap.1\\n  /sbin/swapon /var/swap.1\\n  echo \'/var/swap.1 swap swap defaults 0 0\' | tee -a /etc/fstab\\nfi\\n\\n\\n# Default Route IP\\nIP=$(ip route get 1.1.1.1 | grep -oP \'src \\\\K\\\\S+\')\\n\\n#AWS Internal IP\\n#IP=(`curl -s http://169.254.169.254/latest/meta-data/local-ipv4`)\\n\\n#AWS Public IP\\n#IP=(`curl -s http://169.254.169.254/latest/meta-data/public-ipv4`)\\n\\n#GCP Internal IP\\n#IP=(`curl -H \\"Metadata-Flavor: Google\\" http://169.254.169.254/computeMetadata/v1/instance/network-interfaces/0/ip`)\\n\\n#GCP Public IP\\n#IP=(`curl -H \\"Metadata-Flavor: Google\\" http://169.254.169.254/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip`)\\n\\n# Digital Ocean Public IP\\n#IP=(`hostname -I | cut -d  \' \' -f1 |  tr -d \'\\\\\\\\n\'`)\\n\\n# Public IP from 3rd Party Service\\n#IP=(`curl api.ipify.org`)\\n\\n# OCI Internal IP\\n#IP=(`hostname -I | cut -d  \' \' -f1 |  tr -d \'\\\\\\\\n\'`)\\n\\n# Azure Private IP\\n#IP=(`curl -H Metadata:true \\"http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/privateIpAddress?api-version=2017-04-02&format=text\\"`)\\n\\n# Azure Public IP\\n#IP=(`curl -H Metadata:true \\"http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/publicIpAddress?api-version=2017-04-02&format=text\\"`)\\n\\n#VSphere IP\\n# Replace ens33 with the appropriate network adapter name.\\n#IP=$(/sbin/ip -o -4 addr list ens33 | awk \'{{print $4}}\' | cut -d/ -f1)\\n\\n# If the AutoScaling is configured to create DNS records for the new agents, this value will be populated, and used\\n#   in the agent\'s config\\nif [ -z \\"$GIVEN_FQDN\\" ] ||  [ \\"$GIVEN_FQDN\\" == \\"None\\" ]  ;\\nthen\\n    AGENT_ADDRESS=$IP\\nelse\\n    AGENT_ADDRESS=$GIVEN_FQDN\\nfi\\n\\ncd /tmp\\nwget $KASM_BUILD_URL -O kasm.tar.gz\\ntar -xf kasm.tar.gz\\n\\napt_wait\\nsleep 10\\napt_wait\\n\\n# Install Quemu Agent - Required for Kubevirt environment, optional for others\\n#apt-get update\\n#apt install -y qemu-guest-agent\\n#systemctl enable --now qemu-guest-agent.service\\n\\nbash kasm_release/install.sh -e -S agent -p $AGENT_ADDRESS -m $MANAGER_ADDRESS -i $SERVER_ID -r $PROVIDER_NAME -M $MANAGER_TOKEN\\n\\n# Cleanup the downloaded and extracted files\\nrm kasm.tar.gz\\nrm -rf kasm_release'


  response=$(curl "https://$URL/api/admin/create_vm_provider_config"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b 'username="admin@kasm.local"; session_token="'"$KASM_TOKEN"'"'   --data-raw '{"target_vm_provider_config":{"vm_provider_config_name":"'"$zone_name"'_gcp_provider_config","vm_provider_name":"gcp","max_instances":"'"$max_instance"'","vm_installed_os_type":"linux","startup_script_type":"startup-script","startup_script":"'"$script_body"'","gcp_project":"'"$project"'","gcp_region":"'"$region"'","gcp_zone":"'"$zone"'","gcp_machine_type":"'"$agent_size"'","gcp_image":"'"$image"'","gcp_boot_volume_gb":"'"$agent_disk_size"'","gcp_disk_type":"pd-ssd","gcp_network":"'"$network"'","gcp_subnetwork":"'"$subnet"'","gcp_network_tags":"","gcp_custom_labels":"","gcp_credentials":"","gcp_metadata":"","gcp_service_account":"","gcp_guest_accelerators":"","gcp_config_override":""},"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');       > /dev/null 2>&1;
  vm_provider_config_id=$(echo "$response" | jq -r '.vm_provider_config.vm_provider_config_id');
  vm_provider_config_name=$(echo "$response" | jq -r '.vm_provider_config.vm_provider_config_name');
  echo "VM provider config $vm_provider_config_name with id $vm_provider_config_id created for zone: $zone_name with ID: $zone_id"

  response=$(curl "https://$URL/api/admin/create_autoscale_config"   -k   -s   -H 'accept: application/json'   -H 'content-type: application/json'   -b 'username="admin@kasm.local"; session_token="'"$KASM_TOKEN"'"'   --data-raw '{"target_autoscale_config":{"enabled":false,"server_pool_id":"'"$SERVER_POOL_ID"'","vm_provider_config_id": "'"$vm_provider_config_id"'", "autoscale_type":"Docker Agent","autoscale_config_name":"'"$zone_name"'-autoscale_config","zone_id":"'"$zone_id"'","standby_cores":"'"$avg_cores"'","standby_gpus":"0","standby_memory_mb":"'"$avg_memory_mb"'","agent_cores_override":"'"$avg_cores"'","agent_gpus_override":"0","agent_memory_override_gb":"'"$avg_memory_gb"'","nginx_cert":"'"$CERT_ESCAPED"'","nginx_key":"'"$CERT_KEY_ESCAPED"'","downscale_backoff":"900"},"token":"'"$KASM_TOKEN"'","username":"admin@kasm.local"}');       > /dev/null 2>&1;
  autoscale_config_id=$(echo "$response" | jq -r '.autoscale_config.autoscale_config_id');
  autoscale_config_name=$(echo "$response" | jq -r '.autoscale_config.autoscale_config_name');
  echo "Autoscale config $autoscale_config_name with id $autoscale_config_id created for zone: $zone_name with ID: $zone_id"

done