module "cluster" {
  source           = "../modules/do/postgres-cluster"
  name             = "phazebreak-prod"
  region           = "nyc1"
  postgres_version = "16"
  size             = "db-s-2vcpu-4gb"
  node_count       = 2
}

module "database" {
  source     = "../modules/do/postgres-database"
  cluster_id = module.cluster.id
  db_name    = "prod"
  user_name  = "prod_user"
}
