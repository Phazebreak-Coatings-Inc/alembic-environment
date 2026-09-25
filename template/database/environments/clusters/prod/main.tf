variable "do_token" {}

variable "project_name" {
  type        = string
  description = "Set by the environments CLI from the root pyproject name."
}

provider "digitalocean" {
  token = var.do_token
}

module "cluster" {
  source           = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/postgres-cluster?ref=0.3.0"
  name             = replace(var.project_name, "_", "-")
  region           = "nyc1"
  postgres_version = "18"
  size             = "db-s-2vcpu-4gb"
  node_count       = 2
}

module "prod_database" {
  source     = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/postgres-database?ref=0.3.0"
  cluster_id = module.cluster.id
  db_name    = "prod"
  user_name  = "prod_user"
}

module "staging_database" {
  source     = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/postgres-database?ref=0.3.0"
  cluster_id = module.cluster.id
  db_name    = "staging"
  user_name  = "staging_user"
}

module "logfire" {
  source       = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/logfire?ref=0.3.0"
  project_name = var.project_name
}
