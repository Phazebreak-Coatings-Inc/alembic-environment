resource "digitalocean_database_cluster" "this" {
  name       = var.name
  engine     = "pg"
  version    = var.postgres_version
  size       = var.size
  region     = var.region
  node_count = var.node_count
}

resource "digitalocean_database_firewall" "this" {
  count      = length(var.firewall_rules) > 0 ? 1 : 0
  cluster_id = digitalocean_database_cluster.this.id

  dynamic "rule" {
    for_each = var.firewall_rules
    content {
      type  = rule.value.type
      value = rule.value.value
    }
  }
}
