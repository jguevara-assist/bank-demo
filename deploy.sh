#!/usr/bin/env bash
# deploy.sh — Script de despliegue en OpenShift con Terraform.
# Uso: TF_VAR_ocp_token="sha256~TU_TOKEN_NUEVO" bash deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${SCRIPT_DIR}/terraform"

# ── Verificaciones previas ────────────────────────────────────────────────────
echo "▶ Verificando dependencias..."
command -v terraform >/dev/null 2>&1 || { echo "ERROR: terraform no está instalado."; exit 1; }
command -v oc >/dev/null 2>&1 || echo "  AVISO: oc CLI no encontrado. Algunos comandos post-deploy no estarán disponibles."

if [[ -z "${TF_VAR_ocp_token:-}" ]]; then
  echo "ERROR: Debes exportar TF_VAR_ocp_token antes de ejecutar este script."
  echo "  export TF_VAR_ocp_token='sha256~TU_TOKEN_ROTADO'"
  exit 1
fi

# ── Terraform ─────────────────────────────────────────────────────────────────
cd "${TF_DIR}"

echo ""
echo "▶ Copiando tfvars de ejemplo si no existe terraform.tfvars..."
if [[ ! -f terraform.tfvars ]]; then
  cp terraform.tfvars.example terraform.tfvars
  echo "  Creado terraform.tfvars desde el ejemplo. Revisa los valores antes de continuar."
fi

echo ""
echo "▶ terraform init..."
terraform init

echo ""
echo "▶ terraform plan..."
terraform plan -out=tfplan

echo ""
read -rp "¿Aplicar el plan? [s/N] " confirm
if [[ "${confirm,,}" != "s" ]]; then
  echo "Aplicación cancelada."
  exit 0
fi

echo ""
echo "▶ terraform apply..."
terraform apply tfplan

echo ""
echo "▶ Outputs:"
terraform output

# ── Post-deploy: iniciar build manualmente si es necesario ────────────────────
echo ""
echo "▶ Esperando que el BuildConfig esté listo para iniciar build..."
if command -v oc >/dev/null 2>&1; then
  oc login "$(terraform output -raw ocp_host 2>/dev/null || echo '')" \
    --token="${TF_VAR_ocp_token}" \
    --insecure-skip-tls-verify=true 2>/dev/null || true

  NAMESPACE=$(terraform output -raw namespace 2>/dev/null || echo "demo-bank")
  APP=$(terraform output -raw app_name 2>/dev/null || echo "banco-demo")

  echo "  Iniciando build: oc start-build ${APP} -n ${NAMESPACE} --follow"
  oc start-build "${APP}" -n "${NAMESPACE}" --follow || echo "  AVISO: no se pudo iniciar el build automáticamente. Usa: oc start-build ${APP} -n ${NAMESPACE} --follow"

  echo ""
  echo "  URL de la aplicación:"
  terraform output route_url || true
  echo "  URL OpenAPI (Swagger):"
  terraform output openapi_url || true
else
  echo "  oc CLI no disponible. Inicia el build manualmente:"
  echo "    oc start-build banco-demo -n demo-bank --follow"
fi

echo ""
echo "✅ Despliegue completado."
