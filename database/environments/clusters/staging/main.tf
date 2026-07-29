module "database" {
  source     = "../modules/do/postgres-database"
  cluster_id = module.cluster.id
  db_name    = "staging"
  user_name  = "staging_user"
}
