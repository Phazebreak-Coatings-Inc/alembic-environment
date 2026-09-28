variable "do_token" {
  type      = string
  sensitive = true
}

variable "project_name" {
  type        = string
  description = "Set by the CLI from the root pyproject name, sanitized to lowercase letters, numbers and hyphens."
}
