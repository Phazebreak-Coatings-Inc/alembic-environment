output "database_host" {
  value = module.cluster.host
}

output "database_port" {
  value = module.cluster.port
}

output "database_username" {
  value = module.database.user_name
}

output "database_password" {
  sensitive = true
  value     = module.database.user_password
}

output "database_name" {
  value = module.database.db_name
}
