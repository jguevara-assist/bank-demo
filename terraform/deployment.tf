# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------
# Referencia al ImageStream interno. OpenShift resuelve la imagen
# automáticamente cuando el BuildConfig termina el build.

resource "kubernetes_deployment" "banco_demo" {
  metadata {
    name      = var.app_name
    namespace = var.namespace
    labels = {
      app     = var.app_name
      managed = "terraform"
    }
    annotations = {
      # Fuerza un rollout cuando cambia la imagen en el ImageStream
      "image.openshift.io/triggers" = jsonencode([
        {
          from = {
            kind      = "ImageStreamTag"
            name      = "${var.app_name}:latest"
            namespace = var.namespace
          }
          fieldPath = "spec.template.spec.containers[?(@.name==\"${var.app_name}\")].image"
          paused    = "false"
        }
      ])
    }
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = {
        app = var.app_name
      }
    }

    template {
      metadata {
        labels = {
          app = var.app_name
        }
      }

      spec {
        container {
          name = var.app_name
          # Referencia al registro interno de OpenShift via ImageStream
          image = "image-registry.openshift-image-registry.svc:5000/${var.namespace}/${var.app_name}:latest"

          port {
            container_port = var.app_port
            protocol       = "TCP"
          }

          # Sondas de salud
          liveness_probe {
            http_get {
              path = "/api/customers"
              port = var.app_port
            }
            initial_delay_seconds = 20
            period_seconds        = 15
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/api/customers"
              port = var.app_port
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "256Mi"
            }
          }

          env {
            name  = "PORT"
            value = tostring(var.app_port)
          }
        }

        # OpenShift requiere que el contenedor no corra como root por defecto.
        # El Dockerfile usa python:3.12-slim que arranca como root;
        # OpenShift asigna un UID arbitrario — uvicorn lo acepta sin problemas.
      }
    }
  }

  depends_on = [kubernetes_manifest.buildconfig]
}
