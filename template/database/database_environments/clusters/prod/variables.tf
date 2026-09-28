variable "do_token" {
  type      = string
  sensitive = true
}

variable "project_name" {
  type        = string
  description = "Set by the CLI from the root pyproject name, sanitized to lowercase letters, numbers and hyphens."
}

variable "cluster_region" {
  type        = string
  default     = "nyc1"
  description = "DigitalOcean region slug for the cluster."
}

variable "postgres_version" {
  type        = string
  default     = "18"
  description = "Postgres major version."
}

variable "cluster_size" {
  type        = string
  default     = "db-s-2vcpu-4gb"
  description = "DigitalOcean database size slug. See `doctl databases options slugs --engine pg`."
}

variable "cluster_node_count" {
  type        = number
  default     = 2
  description = "Nodes in the cluster. 1 has no standby; 2 or 3 add standby nodes for failover."

  validation {
    condition     = contains([1, 2, 3], var.cluster_node_count)
    error_message = "cluster_node_count must be 1, 2 or 3."
  }
}
