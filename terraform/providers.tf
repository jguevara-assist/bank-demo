terraform {
  required_version = ">= 1.6.0"

  required_providers {
    # El provider kubernetes maneja recursos nativos de K8s/OpenShift.
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }
}

# Credenciales pasadas siempre como variables de entorno:
#   export TF_VAR_ocp_token="sha256~..."
# Nunca hardcodear el token en este archivo.
provider "kubernetes" {
  host     = var.ocp_host
  token    = var.ocp_token
  insecure = var.ocp_insecure
}
