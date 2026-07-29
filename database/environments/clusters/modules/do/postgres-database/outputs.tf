output "db_name" {
  value = digitalocean_database_db.this.name
}

output "user_name" {
  value = digitalocean_database_user.this.name
}

output "user_password" {
  sensitive = true
  value     = digitalocean_database_user.this.password
}
