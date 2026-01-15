/**
 * # Terraform Module for Hydra Operator
 *
 * This is a Terraform module facilitating the deployment of the hydra charm
 * using the Juju Terraform provider.
 */

resource "juju_application" "application" {
  name        = var.app_name
  trust       = true
  config      = var.config
  constraints = var.constraints
  units       = var.units

  charm {
    name     = "hydra"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
  model_uuid = var.model
}

resource "juju_offer" "oauth_offer" {
  name             = "oauth-offer"
  application_name = juju_application.application.name
  endpoints        = ["oauth"]
  model_uuid       = var.model
}
