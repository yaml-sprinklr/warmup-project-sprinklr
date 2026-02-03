# Order Service Terraform Infrastructure

This directory contains Terraform configuration for deploying the Order Service application with all its dependencies.

## 📁 File Structure

```
terraform/
├── main.tf              # Main infrastructure resources
├── variables.tf         # Variable definitions
├── outputs.tf           # Output definitions
├── providers.tf         # Provider configurations
├── terraform.tfvars     # Development environment values (gitignored)
├── staging.tfvars       # Staging environment values
├── prod.tfvars          # Production environment values
└── README.md            # This file
```

## 🚀 Quick Start

### Prerequisites

1. **Terraform** installed (>= 1.6)
2. **kubectl** configured for your cluster
3. **Docker image** built: `nerdctl --namespace k8s.io build -t order-service:v6 .`

### Deploy to Development

```bash
# Initialize Terraform (first time only)
terraform init

# Preview changes
terraform plan

# Apply changes
terraform apply

# View outputs
terraform output
```

## 🌍 Multiple Environments

### Development (default)

```bash
terraform apply
# Uses terraform.tfvars
```

**Characteristics:**
- 2 replicas
- Small resources (250m CPU, 256Mi memory)
- 1Gi storage
- Monitoring disabled
- Fast iteration

### Staging

```bash
terraform apply -var-file="staging.tfvars"
```

**Characteristics:**
- 3 replicas
- Medium resources (500m CPU, 512Mi memory)
- 10Gi storage
- Monitoring enabled
- Production-like environment

### Production

```bash
terraform apply -var-file="prod.tfvars"
```

**Characteristics:**
- 10 replicas
- Large resources (1-2 CPU cores, 1-2Gi memory)
- 50Gi storage
- Monitoring and autoscaling enabled
- Waits for migrations to complete

## 📝 Customization

### Change Image Version

```bash
# Method 1: Edit terraform.tfvars
app_image_tag = "v7"

# Method 2: Command line override
terraform apply -var="app_image_tag=v7"
```

### Scale Application

```bash
# Edit terraform.tfvars or use CLI
terraform apply -var="app_replica_count=5"
```

### Adjust Resources

Edit the `app_resources` variable in your `.tfvars` file:

```hcl
app_resources = {
  requests = {
    cpu    = "500m"
    memory = "512Mi"
  }
  limits = {
    cpu    = "1000m"
    memory = "1Gi"
  }
}
```

## 🔍 Useful Commands

### View Current State

```bash
# List all resources
terraform state list

# Show specific resource
terraform state show kubernetes_namespace.order_service

# View outputs
terraform output

# View sensitive outputs
terraform output -raw db_password
```

### Debugging

```bash
# Check what will change
terraform plan

# Enable detailed logging
TF_LOG=DEBUG terraform apply

# Target specific resource
terraform apply -target=kubernetes_job_v1.db_migrations
```

### Cleanup

```bash
# Destroy everything
terraform destroy

# Destroy specific environment
terraform destroy -var-file="staging.tfvars"
```

## 📊 What Gets Created

1. **Namespace**: Kubernetes namespace for isolation
2. **PostgreSQL**: Database with persistent storage
3. **ConfigMap**: Non-sensitive configuration
4. **Secret**: Database credentials
5. **Migration Job**: Runs Alembic migrations
6. **Application**: Your FastAPI service (multiple replicas)

## 🔐 Security

- Passwords generated automatically
- Secrets marked as sensitive in Terraform
- ConfigMap/Secret separation
- Resource limits enforced
- RBAC can be added via Helm chart

## 🎯 Access Your Application

After `terraform apply`, use the output commands:

```bash
# Get access instructions
terraform output access_instructions

# Port forward
kubectl port-forward -n order-service svc/order-service-rest-api 8080:8000

# Test API
curl http://localhost:8080/api/v1/orders
```

## 🐛 Troubleshooting

### Migrations Failed

```bash
# Check migration job status
kubectl get job -n order-service

# View migration logs
kubectl logs -n order-service -l component=migrations

# Delete failed job and reapply
kubectl delete job order-service-migrations -n order-service
terraform apply
```

### Pod Crashes

```bash
# Check pod status
kubectl get pods -n order-service

# View logs
kubectl logs -n order-service -l app=order-service --tail=100

# Describe pod for events
kubectl describe pod -n order-service <pod-name>
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
kubectl get pods -n order-service | grep postgres

# Port forward to database
kubectl port-forward -n order-service svc/order-service-postgres-postgresql 5432:5432

# Connect with psql
export PGPASSWORD=$(terraform output -raw db_password)
psql -h localhost -U postgres -d appdb
```

## 📚 Variable Reference

See `variables.tf` for all available variables and their validation rules.

Key variables:
- `environment`: dev, staging, or prod
- `app_replica_count`: Number of application pods
- `app_image_tag`: Docker image version
- `postgres_storage_size`: Database storage size
- `enable_metrics`: Enable Prometheus monitoring
- `migration_wait_for_completion`: Wait for migrations

## 🔄 Workflow

Typical development workflow:

```bash
# 1. Build new image
nerdctl --namespace k8s.io build -t order-service:v7 .

# 2. Update image tag
# Edit terraform.tfvars: app_image_tag = "v7"

# 3. Preview changes
terraform plan

# 4. Apply changes
terraform apply

# 5. Verify deployment
kubectl get pods -n order-service
kubectl logs -n order-service -l app=order-service
```

## 🎓 Learning Resources

- Terraform variables: https://developer.hashicorp.com/terraform/language/values/variables
- Terraform outputs: https://developer.hashicorp.com/terraform/language/values/outputs
- Kubernetes provider: https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs
- Helm provider: https://registry.terraform.io/providers/hashicorp/helm/latest/docs
