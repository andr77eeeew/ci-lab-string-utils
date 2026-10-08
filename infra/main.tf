terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  registry_auth {
    address     = "ghcr.io"
    config_file = pathexpand("~/.docker/config.json")
  }
}

resource "docker_image" "app" {
  name = var.image_name
}

resource "docker_container" "app" {
  name     = "ci-lab-deploy"
  image    = docker_image.app.image_id
  command  = ["pytest", "-v"]
  rm       = false
  must_run = false
}

output "container_id" {
  description = "Ідентифікатор створеного контейнера"
  value       = docker_container.app.id
}

output "image_id" {
  description = "Ідентифікатор Docker-образу"
  value       = docker_image.app.image_id
}