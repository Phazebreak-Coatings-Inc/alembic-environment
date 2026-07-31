variable "do_token" {}

provider "digitalocean" {
  token = var.do_token
} 

module "cluster" {
  source           = "../modules/do/postgres-cluster"
  name             = "alembic-environment"
  region           = "nyc1"
  postgres_version = "18"
  size             = "db-s-2vcpu-4gb"
  node_count       = 2
}

module "prod_database" {
  source     = "../modules/do/postgres-database"
  cluster_id = module.cluster.id
  db_name    = "prod"
  user_name  = "prod_user"
}

module "staging_database" {
  source     = "../modules/do/postgres-database"
  cluster_id = module.cluster.id
  db_name    = "staging"
  user_name  = "staging_user"
}

