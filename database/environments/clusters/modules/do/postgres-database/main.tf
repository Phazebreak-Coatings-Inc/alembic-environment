resource "digitalocean_database_db" "this" {
  cluster_id = var.cluster_id
  name       = var.db_name
}

resource "digitalocean_database_user" "this" {
  cluster_id = var.cluster_id
  name       = var.user_name
}
