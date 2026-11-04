# ---------------------------------------------------------------------------
# ImageStream
# ---------------------------------------------------------------------------
# OpenShift almacena el resultado del build en un ImageStream.
# El Deployment referencia al tag "latest" de este stream.

resource "kubernetes_manifest" "imagestream" {
  manifest = {
    apiVersion = "image.openshift.io/v1"
    kind       = "ImageStream"
    metadata = {
      name      = var.app_name
      namespace = var.namespace
      labels = {
        app     = var.app_name
        managed = "terraform"
      }
    }
    spec = {
      lookupPolicy = {
        local = true
      }
    }
  }

  depends_on = [kubernetes_namespace.demo_bank]
}

# ---------------------------------------------------------------------------
# BuildConfig (Docker strategy)
# ---------------------------------------------------------------------------
# Lee el Dockerfile del repositorio Git y construye la imagen en el cluster.
# El contexto es banco_demo/ dentro del repo (git_context_dir).

resource "kubernetes_manifest" "buildconfig" {
  manifest = {
    apiVersion = "build.openshift.io/v1"
    kind       = "BuildConfig"
    metadata = {
      name      = var.app_name
      namespace = var.namespace
      labels = {
        app     = var.app_name
        managed = "terraform"
      }
    }
    spec = {
      source = {
        type = "Git"
        git = {
          uri = var.git_repo
          ref = var.git_ref
        }
        contextDir = var.git_context_dir
      }
      strategy = {
        type = "Docker"
        dockerStrategy = {
          dockerfilePath = "Dockerfile"
        }
      }
      output = {
        to = {
          kind = "ImageStreamTag"
          name = "${var.app_name}:latest"
        }
      }
      triggers = [
        {
          type = "ConfigChange"
        },
        {
          type        = "ImageChange"
          imageChange = {}
        }
      ]
      runPolicy = "Serial"
    }
  }

  depends_on = [kubernetes_manifest.imagestream]
}
