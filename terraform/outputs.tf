# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "The Juju application name"
  value       = juju_application.application.name
}

output "requires" {
  description = "The Juju integrations that the charm requires"
  value = {
    pg-database      = "pg-database"
    public-route     = "public-route"
    internal-route   = "internal-route"
    ui-endpoint-info = "ui-endpoint-info"
    logging          = "logging"
    tracing          = "tracing"
  }
}

output "provides" {
  description = "The Juju integrations that the charm provides"
  value = {
    oauth               = "oauth"
    hydra-endpoint-info = "hydra-endpoint-info"
    metrics-endpoint    = "metrics-endpoint"
    grafana-dashboard   = "grafana-dashboard"
  }
}


