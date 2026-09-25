terraform {
  required_version = ">= 1.9"
  cloud {}
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
    logfire = {
      source  = "pydantic/logfire"
      version = ">= 0.1.0, < 0.2.0"
    }
  }
}
