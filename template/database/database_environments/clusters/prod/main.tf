terraform {
  required_version = ">= 1.9"
  cloud {}

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
    logfire = {
      source  = "pydantic/logfire"
      version = ">= 0.1.0, < 0.2.0"
    }
  }
}

provider "digitalocean" {
  token = var.do_token
}

module "cluster" {
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/postgres-cluster?ref=terraform-pattern"

  name             = var.project_name
  region           = "nyc1"
  postgres_version = "18"
  size             = "db-s-2vcpu-4gb"
  node_count       = 2
}

module "prod_database" {
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/postgres-database?ref=terraform-pattern"

  cluster_id = module.cluster.id
  db_name    = "prod"
  user_name  = "prod_user"
}

module "staging_database" {
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/postgres-database?ref=terraform-pattern"

  cluster_id = module.cluster.id
  db_name    = "staging"
  user_name  = "staging_user"
}

module "logfire" {
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/logfire?ref=terraform-pattern"

  project_name = var.project_name
}

output "database_host" {
  value = module.cluster.host
}

output "database_port" {
  value = module.cluster.port
}

output "admin_username" {
  value = module.cluster.admin_username
}

output "admin_password" {
  value     = module.cluster.admin_password
  sensitive = true
}

output "prod_name" {
  value = module.prod_database.db_name
}

output "prod_username" {
  value = module.prod_database.user_name
}

output "prod_password" {
  value     = module.prod_database.user_password
  sensitive = true
}

output "staging_name" {
  value = module.staging_database.db_name
}

output "staging_username" {
  value = module.staging_database.user_name
}

output "staging_password" {
  value     = module.staging_database.user_password
  sensitive = true
}

output "logfire_token" {
  value     = module.logfire.write_token
  sensitive = true
}
