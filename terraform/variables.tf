variable "ocp_host" {
  description = "URL de la API de OpenShift (ej. https://api.cluster.example.com:6443)."
  type        = string
  default     = "https://api.itz-m23snt.infra01-lb.wdc04.techzone.ibm.com:6443"
}

variable "ocp_token" {
  description = "Token de autenticación (sha256~...). Pásalo como TF_VAR_ocp_token o -var."
  type        = string
  sensitive   = true
}

variable "ocp_insecure" {
  description = "Saltar verificación TLS del cluster (true en entornos de lab con cert auto-firmado)."
  type        = bool
  default     = true
}

variable "namespace" {
  description = "Proyecto/Namespace de OpenShift donde se desplegará la aplicación."
  type        = string
  default     = "demo-bank"
}

variable "app_name" {
  description = "Nombre base de la aplicación."
  type        = string
  default     = "banco-demo"
}

variable "git_repo" {
  description = "URL del repositorio Git con el código fuente."
  type        = string
  default     = "https://github.com/jguevara-assist/bank-demo"
}

variable "git_ref" {
  description = "Rama o tag del repositorio Git."
  type        = string
  default     = "main"
}

variable "git_context_dir" {
  description = "Subdirectorio dentro del repo que contiene el Dockerfile (vacío = raíz del repo)."
  type        = string
  default     = ""
}

variable "app_port" {
  description = "Puerto que expone el contenedor."
  type        = number
  default     = 8000
}

variable "replicas" {
  description = "Número de réplicas del Deployment."
  type        = number
  default     = 1
}

variable "route_host" {
  description = "Hostname de la Route. Si está vacío, OpenShift genera uno automáticamente."
  type        = string
  default     = ""
}
