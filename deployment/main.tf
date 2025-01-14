terraform {
    required_providers {
        juju = {
            version = ">= 0.15.0"
            source  = "juju/juju"
        }
    }
}

variable "cloud" {
  type        = string
}

variable "client_id" {
  type        = string
}

variable "client_secret" {
  type        = string
}

variable "jimm_url" {
  type        = string
}

variable "model" {
  type        = string
}

variable "charm" {
  description = "The configurations of the application."
  type = object({
    name    = optional(string, "hydra")
    units   = optional(number, 1)
    base    = optional(string, "ubuntu@22.04")
    trust   = optional(string, true)
    config  = optional(map(string), {})
  })
  default = {}
}

variable "application_name" {
  type = string
}

variable "channel" {
  type = string
}

variable "revision" {
  type = number
}

provider "juju" {
    controller_addresses = var.jimm_url

    client_id     = var.client_id
    client_secret = var.client_secret

}

data "juju_model" "model" {
   name = var.model
}


resource "juju_application" "application" {
  model = data.juju_model.model.name
  name  = var.application_name
  trust = var.charm.trust
  units = var.charm.units

  charm {
    name    = var.charm.name
    channel = var.channel
    base    = var.charm.base
    revision = var.revision
  }

  config = var.charm.config

}
