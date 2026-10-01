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
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/postgres-cluster?ref=0.3.1"

  name             = var.project_name
  region           = var.cluster_region
  postgres_version = var.postgres_version
  size             = var.cluster_size
  node_count       = var.cluster_node_count
}

module "prod_database" {
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/postgres-database?ref=0.3.1"

  cluster_id = module.cluster.id
  db_name    = "prod"
  user_name  = "prod_user"
}

module "staging_database" {
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/postgres-database?ref=0.3.1"

  cluster_id = module.cluster.id
  db_name    = "staging"
  user_name  = "staging_user"
}

module "logfire" {
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/logfire?ref=0.3.1"

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
