output "namespace" {
  description = "Namespace/Proyecto donde se desplegó la aplicación."
  value       = kubernetes_namespace.demo_bank.metadata[0].name
}

output "app_name" {
  description = "Nombre de la aplicación."
  value       = var.app_name
}

output "git_repo" {
  description = "Repositorio Git usado para el BuildConfig."
  value       = var.git_repo
}

output "internal_service_url" {
  description = "URL interna del Service (accesible solo dentro del cluster)."
  value       = "http://${kubernetes_service.banco_demo.metadata[0].name}.${var.namespace}.svc.cluster.local:${var.app_port}"
}

output "route_url" {
  description = "URL pública de la aplicación (disponible una vez que la Route se asigne). Añade /docs para OpenAPI."
  value       = "https://banco-demo-${var.namespace}.apps.itz-m23snt.infra01-lb.wdc04.techzone.ibm.com"
}

output "openapi_url" {
  description = "URL de la documentación OpenAPI Swagger."
  value       = "https://banco-demo-${var.namespace}.apps.itz-m23snt.infra01-lb.wdc04.techzone.ibm.com/docs"
}

output "build_command" {
  description = "Comando oc para disparar un build manual si el trigger automático no funciona."
  value       = "oc start-build ${var.app_name} -n ${var.namespace} --follow"
}
