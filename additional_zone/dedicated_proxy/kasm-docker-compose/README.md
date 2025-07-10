# Kasm Docker Compose
This project should be used for development and testing purposes only. It is not intended to be used in production environments, use either the traditional installation methods covered in the Kasm documentation or Kubernetes. This project seeks to mimic a Kubernetes deployment to the extent possible, to make it easier for developers to run the Kasm stack from source and have it behave like it does when running in Kubernetes.

## Deployment

The first step is to edit the `.env` file to ensure it references the correct images. By default it points to the develop tag for all images. If you are working on a feature branch, you will want to edit the variables. Most of the images use the first two variables, however, the rdp gateway, rdp https gateway, and database are managed in different projects and thus may or may not have a matching image when you are testing a feature branch. Here is an exmaple of an `.env` file that has been modified to test a branch where the kasm_backend and redemption projects have matching branch names. Note that the matching `IMAGE_PRIVATE` variables have a value of **-private**, which is required if you are referencing private images. For public images this value needs to be empty.

```bash
IMAGE_TAG=feature_KASM-5905-add-in-fine-grained-permission-controls-from-client-settings
IMAGE_PRIVATE="-private"

RDP_IMAGE_TAG=feature_KASM-5905-add-in-fine-grained-permission-controls-from-client-settings
RDP_IMAGE_PRIVATE="-private"

RDPHTTPS_IMAGE_TAG=develop
RDPHTTPS_IMAGE_PRIVATE=

DB_IMAGE_TAG=develop
DB_IMAGE_PRIVATE=
```

Use the following commands to prepare and deploy a Kasm stack in Docker compose. This assumes that Docker and the Docker Compose v2 plugin are installed on the system.

```bash
git clone https://gitlab.com/kasm-technologies/playground/kasm-docker-compose.git
cd kasm-docker-compose

# Generate an SSL Cert and key to be used by different services
sudo openssl req -nodes -x509 -sha256 -newkey rsa:4096 \
  -keyout certs/server.key \
  -out certs/server.crt \
  -days 356 \
  -subj "/C=US/ST=VA/L=None/O=None/OU=DoFu/CN=ma-prototype.kasm.technology/emailAddress=none@none.none"  \
  -addext "subjectAltName = DNS:ma-prototype.kasm.technology"
sudo chown 1000:1000 certs/server.*

sudo docker compose up
```

**The default admin password, and all other default creds/tokens, are in the docker-compose.yaml file** as environmental variables in the kasm-api service.

## Running from source
The docker compose deployment can easily be modified to run from source. The kasm_backend README should be followed to get the latest instructions on building components, however, the following can be used as a general reference.

```bash
cd kasm-docker-compose

# get backend source
git clone https://gitlab.com/kasm-technologies/internal/kasm_backend.git

# build API image
cd kasm_backend
sudo docker build -t kasmweb/api-dev:dev -f api_server/Dockerfile.kasmweb.api.dev .

# Build manager image
sudo docker build -t kasmweb/manager-dev:dev -f api_server/Dockerfile.kasmweb.manager.dev .

# Build Guac image
git submodule init
git submodule update --remote --merge
sudo docker build -t kasmweb/kasm-guac:deps -f guac_server/Dockerfile.kasmweb.kasmguac.deps .
sudo docker build -t kasmweb/kasm-guac-dev:dev -f guac_server/Dockerfile.kasmweb.kasmguac .

# Build kasm proxy (with web code)
sudo docker build --pull --build-arg KASMWEB_BRANCH_NAME=develop -f build/services/service_containers/Dockerfile.kasmweb.proxy -t kasmweb/proxy-dev:dev .

# get redemption source
cd ..
git clone https://gitlab.com/kasm-technologies/internal/redemption.git
cd redemption
sudo docker build -t kasmweb/rdp-gateway-dev:dev -f Dockerfile .

# get rdpgw source
git clone https://gitlab.com/kasm-technologies/internal/rdpgw.git
# build rdpgw image
cd rdpgw
sudo docker build -t kasmweb/rdp-https-gateway-dev:dev -f dev/docker/Dockerfile .
```

Once you have your target images built, edit the docker-compose.yaml file. Each service has two image elements defined, with one commented out, swap them, leaving the one ending in `dev:dev` left untagged. For images that support running from source, there is a commented out volume mapping, uncomment that line for each respective image. Shutdown the project if it is running, ensure stopped containers are removed, and bring the project back up.

```bash
# bring deployment down
sudo docker compose down

# check for any stopped containers
sudo docker ps -a

# remove any stopped containers
sudo docker rm kasm_proxy

# start the services back up
sudo docker compose up
``` 

**Kasmweb Project From Source**
The docker-compose.yaml file already contains a service for a node container, which is disabled. Edit the compose file, commenting out the profiles section like so.

```bash
  nodeserver:
    container_name: nodeserver
    image: node:20-bookworm
    networks:
      - kasm_default_network
    volumes:
      - ./kasmweb:/src
    #profiles:
    #  -donotstart
    entrypoint: [ "bash", "-c", "cd /src && npm install --force && npm start" ]
```

Additionally, you will need to edit the `conf/nginx/services.d/website.conf` file, swapping the comment on the following two lines, so that the proxy_pass directive is uncomm
ented and the root directive is commented out.

```bash
        #root /srv/www;
        proxy_pass http://nodeserver:9001;
```

With those edits made, you can bring things back up.

```bash
# Make sure all services are down if not already down
sudo docker compose down

sudo docker compose up -d
```

## Maintaining This Project
There will be a branch in this project for each release of Kasm Workspaces, starting with the first version that supports Kubernetes (1.16.0). For each major release there are certain things that need to be updated in this project.

### NGINX Configurations
The NGINX configurations in this project are largely copied from a single server installation of Kasm Workspaces, with slight modifications. The major difference is that docker compose supports underscores in hostnames, while Kubernetes does not. Since Kasm Workspaces uses underscores in service names within the docker compose files, we need to modify the nginx configs to use dashes. Of note, the compose file in this project uses dashes, as this project seeks to have as much parity with a Kubernetes deployment as possible.

The following is accurate as of 1.16.0 developer preview.

Copy configurations from kasm_backend and run the following commands.

```bash
cp -R kasm_backend/install/conf/nginx/* kasm-docker-compose/conf/nginx/
rm -rf kasm-docker-compose/conf/nginx/containers.d
rm kasm-docker-compose/conf/nginx/services.d/rdp_https_gateway_guac.conf
cd kasm-docker-compose

sed -r -i 's#kasm_(api|guac|manager|share):#kasm-\1:#g' conf/nginx/upstream_*.conf
sed -i 's#kasm_rdp_https_gateway:#kasm-rdp-https-gateway:#g' conf/nginx/upstream_rdp_https_gateway.conf
sed -i 's#rdp_gateway:#kasm-rdp-gateway:#g' conf/nginx/upstream_rdp_gateway.conf
sed -r -i 's#kasm_guac:#kasm-guac:#g' conf/nginx/services.d/kasmguac.conf
```

You then need to edit rdp_https_gateway_webapp.conf remove the sub request and hard code the service name `kasm-rdp-https-gateway` on port 443.
