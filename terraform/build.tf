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
# contextDir se omite si git_context_dir está vacío (Dockerfile en la raíz).
#
# NOTA: Los triggers se omiten del manifest porque OpenShift los enriquece
# después del apply (agrega lastTriggeredImageID y otros campos), lo que hace
# que el provider detecte drift y falle con "element has vanished".
# OpenShift añade los triggers ConfigChange e ImageChange por defecto.
# lifecycle.ignore_changes protege contra cualquier otra mutación del API server.

locals {
  # Fuente Git: incluye contextDir solo si tiene valor (evita enviar "" al API).
  _git_source_base = {
    type = "Git"
    git = {
      uri = var.git_repo
      ref = var.git_ref
    }
    contextDir = var.git_context_dir != "" ? var.git_context_dir : null
  }
  git_source = { for k, v in local._git_source_base : k => v if v != null }
}

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
      source = local.git_source
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
      runPolicy = "Serial"
      # triggers se omite: OpenShift los gestiona internamente.
      # Usa "oc start-build banco-demo -n demo-bank" para builds manuales.
    }
  }

  # ignore_changes evita que las mutaciones que hace el API server de OpenShift
  # (enriquecer triggers, añadir status, etc.) rompan el plan en ejecuciones
  # posteriores de terraform apply.
  lifecycle {
    ignore_changes = [manifest]
  }

  depends_on = [kubernetes_manifest.imagestream]
}
