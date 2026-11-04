# ---------------------------------------------------------------------------
# Namespace (Proyecto OpenShift)
# ---------------------------------------------------------------------------
# OpenShift crea un Project cuando se crea un Namespace con la anotación
# openshift.io/requester. Si el proyecto ya existe, Terraform lo adopta.

resource "kubernetes_namespace" "demo_bank" {
  metadata {
    name = var.namespace
    labels = {
      app     = var.app_name
      env     = "demo"
      managed = "terraform"
    }
    annotations = {
      "openshift.io/display-name" = "Banco Demo — Créditos y Fraude"
      "openshift.io/description"  = "Datos sintéticos. No usar para decisiones crediticias reales."
    }
  }
}
