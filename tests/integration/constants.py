# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
HYDRA_APP = METADATA["name"]
HYDRA_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
DB_APP = "postgresql-k8s"
CA_APP = "self-signed-certificates"
LOGIN_UI_APP = "identity-platform-login-ui-operator"
TRAEFIK_CHARM = "traefik-k8s"
ISTIO_CHARM = "istio-k8s"
ISTIO_INGRESS_CHARM = "istio-ingress-k8s"
ISTIO_INGRESS_PUBLIC_APP = "istio-ingress-public"
ISTIO_INGRESS_ADMIN_APP = "istio-ingress-admin"
ISTIO_CHANNEL = "2/stable"
CLIENT_SECRET = "secret"
CLIENT_REDIRECT_URIS = ["https://example.com"]
PUBLIC_INGRESS_DOMAIN = "public"
ADMIN_INGRESS_DOMAIN = "admin"
