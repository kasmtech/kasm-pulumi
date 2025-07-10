# Required GCP Permissions

- **`roles/serviceusage.serviceUsageAdmin`**  
  Required if `auto_enable_gcp_api=true` is set in the Pulumi stack configuration. This allows the Pulumi script to automatically enable all required GCP APIs in the specified project.
- **`roles/cloudsql.admin`**  
  Grants permissions to create a Cloud SQL (PostgreSQL) instance, along with managing databases and database users.
- **`roles/dns.admin`**  
  Allows the creation and management of Cloud DNS zones and DNS record sets.
- **`roles/servicenetworking.networksAdmin`**  
  Enables creation of private service connections between the VPC network and services like Cloud SQL. This is necessary for connecting the Cloud SQL instance to the VPC.
- **`roles/compute.admin`**  
  Grants full control over Compute Engine resources including VPC networks, subnets, firewall rules, routers, NAT gateways, static IP addresses, and VM instances.
- **`roles/container.admin`**  
  Provides full access to create and manage GKE (Google Kubernetes Engine) clusters, as well as access the clusters once created.
- **`roles/iam.serviceAccountUser`**  
  Grants permissions to use service accounts. This role is required to ensure that GKE clusters and VMs can work with the appropriate service account.
- **`roles/certificatemanager.editor`**
  Grants permissions to create and delete GCP managed certificates. 