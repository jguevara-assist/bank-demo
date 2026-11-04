# ---------------------------------------------------------------------------
# Service (ClusterIP)
# ---------------------------------------------------------------------------
# Expone el Deployment internamente en el cluster en el puerto 8000.

resource "kubernetes_service" "banco_demo" {
  metadata {
    name      = var.app_name
    namespace = var.namespace
    labels = {
      app     = var.app_name
      managed = "terraform"
    }
  }

  spec {
    selector = {
      app = var.app_name
    }

    port {
      name        = "http"
      port        = var.app_port
      target_port = var.app_port
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }

  depends_on = [kubernetes_deployment.banco_demo]
}

# ---------------------------------------------------------------------------
# Route (OpenShift)
# ---------------------------------------------------------------------------
# Expone el Service al exterior con terminación TLS edge (HTTPS automático).
# Si route_host está vacío, OpenShift genera el hostname:
#   banco-demo-demo-bank.apps.itz-m23snt.infra01-lb.wdc04.techzone.ibm.com

locals {
  # Construimos el spec de la Route.
  # "host" se incluye solo cuando route_host tiene valor; de lo contrario se omite
  # usando un for expression que filtra claves con valor null.
  _route_spec_with_nulls = {
    host = var.route_host != "" ? var.route_host : null
    port = {
      targetPort = "http"
    }
    to = {
      kind   = "Service"
      name   = var.app_name
      weight = 100
    }
    tls = {
      termination                   = "edge"
      insecureEdgeTerminationPolicy = "Redirect"
    }
    wildcardPolicy = "None"
  }

  # Elimina las claves con valor null para que OpenShift no reciba "host: null"
  route_spec = { for k, v in local._route_spec_with_nulls : k => v if v != null }
}

resource "kubernetes_manifest" "route" {
  manifest = {
    apiVersion = "route.openshift.io/v1"
    kind       = "Route"
    metadata = {
      name      = var.app_name
      namespace = var.namespace
      labels = {
        app     = var.app_name
        managed = "terraform"
      }
    }
    spec = local.route_spec
  }

  depends_on = [kubernetes_service.banco_demo]
}
