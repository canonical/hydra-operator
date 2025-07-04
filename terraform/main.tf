/**
 * # Terraform Module for Hydra Operator
 *
 * This is a Terraform module facilitating the deployment of the hydra charm
 * using the Juju Terraform provider.
 */

resource "juju_application" "hydra" {
  name        = var.app_name
  model       = var.model_name
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
}

resource "juju_offer" "oauth_offer" {
  name             = "oauth-offer"
  model            = var.model_name
  application_name = juju_application.hydra.name
  endpoints         = ["oauth"]
}
