# ejemplos_api.sh — Ejemplos de solicitud curl para las 5 operaciones
# Banco Demo — Créditos y Fraude v1.1.0
#
# Ajusta BASE_URL según el entorno:
#   Local:     export BASE_URL=http://localhost:8000
#   OpenShift: export BASE_URL=https://banco-demo-demo-bank.apps.itz-m23snt.infra01-lb.wdc04.techzone.ibm.com
#
# Si DEMO_API_KEY está configurada, añade: -H "X-API-Key: $DEMO_API_KEY"

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== 1. list_demo_customers ==="
curl -s "$BASE_URL/api/customers" | python3 -m json.tool

echo ""
echo "=== 2. get_customer_credit_profile (DEMO-001) ==="
curl -s "$BASE_URL/api/customers/DEMO-001/profile" | python3 -m json.tool

echo ""
echo "=== 3. calculate_demo_credit_score (DEMO-003 — score alto) ==="
curl -s "$BASE_URL/api/customers/DEMO-003/score" | python3 -m json.tool

echo ""
echo "=== 3b. calculate_demo_credit_score (DEMO-012 — datos insuficientes) ==="
curl -s "$BASE_URL/api/customers/DEMO-012/score" | python3 -m json.tool

echo ""
echo "=== 4. check_demo_fraud_signals (alerta HIGH: R1 + R3) ==="
curl -s -X POST "$BASE_URL/api/fraud/check" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-001","amount":25000000,"device_id":"DEV-AAA"}' \
  | python3 -m json.tool

echo ""
echo "=== 4b. check_demo_fraud_signals (alerta LOW) ==="
curl -s -X POST "$BASE_URL/api/fraud/check" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-007","amount":5000000,"device_id":"DEV-NUEVO-XYZ"}' \
  | python3 -m json.tool

echo ""
echo "=== 5a. evaluate_demo_loan_application — APROBADO (DEMO-003) ==="
curl -s -X POST "$BASE_URL/api/loans/evaluate" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-003","amount":20000000,"term_months":36,"annual_effective_rate":0.18}' \
  | python3 -m json.tool

echo ""
echo "=== 5b. evaluate_demo_loan_application — RECHAZADO (DEMO-010) ==="
curl -s -X POST "$BASE_URL/api/loans/evaluate" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-010","amount":5000000,"term_months":24,"annual_effective_rate":0.18}' \
  | python3 -m json.tool

echo ""
echo "=== 5c. evaluate_demo_loan_application — REVISIÓN POR ALERTA (DEMO-001) ==="
curl -s -X POST "$BASE_URL/api/loans/evaluate" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-001","amount":25000000,"term_months":60,"annual_effective_rate":0.18}' \
  | python3 -m json.tool

echo ""
echo "=== 5d. evaluate_demo_loan_application — DATOS INSUFICIENTES (DEMO-012) ==="
curl -s -X POST "$BASE_URL/api/loans/evaluate" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-012","amount":10000000,"term_months":24,"annual_effective_rate":0.18}' \
  | python3 -m json.tool
