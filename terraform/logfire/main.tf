terraform {
  required_providers {
    logfire = {
      source  = "pydantic/logfire"
      version = ">= 0.1.0, < 0.2.0"
    }
  }
}

variable "project_name" {
  type        = string
  description = "Logfire project name. Usually the root project name with a _database suffix."
}

resource "logfire_project" "this" {
  name = var.project_name
}

resource "logfire_write_token" "app" {
  project_id = logfire_project.this.id
}

output "project_id" {
  value = logfire_project.this.id
}

output "write_token" {
  value     = logfire_write_token.app.token
  sensitive = true
}
