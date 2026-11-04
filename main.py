"""
main.py — Servicio FastAPI: Banco Demo — Créditos y Fraude.

Endpoints:
  GET  /api/customers                         → list_demo_customers
  GET  /api/customers/{customer_id}/profile   → get_customer_credit_profile
  GET  /api/customers/{customer_id}/score     → calculate_demo_credit_score
  POST /api/fraud/check                       → check_demo_fraud_signals
  POST /api/loans/evaluate                    → evaluate_demo_loan_application
  GET  /                                      → Interfaz HTML

Autenticación:
  Este servicio de demostración NO implementa autenticación empresarial.
  Opcionalmente, se puede activar una API key mínima estableciendo la variable
  de entorno DEMO_API_KEY. Si está definida, todos los endpoints /api/* exigen
  el header `X-API-Key: <valor>`. Si no está definida, los endpoints son
  públicos (apropiado solo para entornos de desarrollo/demo locales).

Servers:
  La URL base del servidor se controla con la variable de entorno SERVER_URL.
  Si no está definida, el contrato OpenAPI no incluye el campo `servers`,
  lo que permite que Swagger UI utilice la URL relativa del navegador y que
  webMethods / MCP inyecten su propio base URL al integrar el contrato.

Prioridad de decisión en evaluate_demo_loan_application:
  1. not_found          — cliente inexistente
  2. insufficient_data  — ingresos == 0
  3. rejected           — criterio crediticio (score < 500 o carga > 60 %).
                          El rechazo crediticio tiene prioridad sobre fraude:
                          si la solicitud ya es rechazada, la alerta HIGH no
                          cambia la decisión (sí aparece en fraud_check).
  4. review_fraud_alert — aprobada crediticiamente pero alerta HIGH de fraude
  5. review             — rango intermedio
  6. approved           — score >= 650 y carga <= 40 % y sin alerta HIGH

device_id en evaluate_demo_loan_application:
  El endpoint no recibe device_id del solicitante. Internamente usa
  "WEB-PORTAL" como identificador genérico del canal web. Esto significa
  que R2 (dispositivo multicliente) se activará solo si el historial ya
  contiene solicitudes de otro cliente desde "WEB-PORTAL". Para verificar
  fraude con el device_id real del dispositivo, usa POST /api/fraud/check.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Path, Security, status
from fastapi.responses import HTMLResponse
from fastapi.security.api_key import APIKeyHeader

from core import (
    _CUSTOMERS,
    _CUSTOMER_INDEX,
    _REQUESTS,
    calculate_credit_score,
    check_fraud_signals,
    evaluate_loan,
)
from models import (
    CustomerListResponse,
    CustomerProfileResponse,
    CreditScoreResponse,
    FraudCheckRequest,
    FraudSignalResponse,
    LoanEvaluationRequest,
    LoanEvaluationResponse,
)

# ---------------------------------------------------------------------------
# Configuración desde entorno
# ---------------------------------------------------------------------------

_DEMO_API_KEY: Optional[str] = os.environ.get("DEMO_API_KEY")
_SERVER_URL: Optional[str] = os.environ.get("SERVER_URL")

# ---------------------------------------------------------------------------
# Autenticación opcional por API key
# ---------------------------------------------------------------------------
# Si DEMO_API_KEY está definida, todos los endpoints /api/* exigen el header
# X-API-Key. Si no está definida, los endpoints son públicos.
#
# Cambio mínimo para proteger el backend en producción:
#   export DEMO_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
#   # Luego pasa el header en cada llamada:
#   curl -H "X-API-Key: <valor>" http://localhost:8000/api/customers
#
# Para una integración webMethods / MCP, configura el mismo valor como
# secreto en el conector y mapearlo al header X-API-Key.

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(_api_key_header)) -> None:
    """
    Dependencia de autenticación por API key.
    - Si DEMO_API_KEY no está definida en el entorno: sin autenticación.
    - Si DEMO_API_KEY está definida: el header X-API-Key debe coincidir.
    """
    if _DEMO_API_KEY is None:
        return  # Sin autenticación configurada
    if api_key != _DEMO_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente. Incluye el header X-API-Key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


# ---------------------------------------------------------------------------
# Aplicación FastAPI
# ---------------------------------------------------------------------------

_servers = [{"url": _SERVER_URL, "description": "Servidor configurado por entorno"}] if _SERVER_URL else []

app = FastAPI(
    title="Banco Demo — Créditos y Fraude",
    description=(
        "API de demostración con datos sintéticos para integración con IBM webMethods / MCP.\n\n"
        "**No utilizar para decisiones crediticias reales.**\n\n"
        "### Autenticación\n"
        "Sin autenticación por defecto. Para activar API key mínima, define la variable de entorno "
        "`DEMO_API_KEY` y pasa el header `X-API-Key` en cada solicitud.\n\n"
        "### Servidor\n"
        "Define `SERVER_URL` para incluir la URL base en el contrato OpenAPI exportado "
        "(ej. `https://banco-demo-demo-bank.apps.cluster.example.com`)."
    ),
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    servers=_servers if _servers else None,
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get(
    "/api/customers",
    summary="Listar clientes de demostración",
    operation_id="list_demo_customers",
    tags=["Clientes"],
    response_model=CustomerListResponse,
    dependencies=[Depends(verify_api_key)],
)
def list_demo_customers() -> CustomerListResponse:
    """Retorna la lista de los 12 clientes sintéticos con sus datos financieros."""
    return CustomerListResponse(
        total=len(_CUSTOMERS),
        customers=_CUSTOMERS,
        disclaimer="Datos sintéticos. No representan personas reales.",
    )


@app.get(
    "/api/customers/{customer_id}/profile",
    summary="Perfil crediticio del cliente",
    operation_id="get_customer_credit_profile",
    tags=["Clientes"],
    response_model=CustomerProfileResponse,
    responses={404: {"description": "Cliente no encontrado."}},
    dependencies=[Depends(verify_api_key)],
)
def get_customer_credit_profile(
    customer_id: str = Path(..., examples=["DEMO-001"]),
) -> CustomerProfileResponse:
    """Devuelve los datos financieros del cliente y el historial de solicitudes previas."""
    customer = _CUSTOMER_INDEX.get(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Cliente '{customer_id}' no encontrado.")

    history = [r for r in _REQUESTS if r["customer_id"] == customer_id]

    return CustomerProfileResponse(
        customer=customer,
        request_history=history,
        disclaimer="Datos sintéticos. No representan personas reales.",
    )


@app.get(
    "/api/customers/{customer_id}/score",
    summary="Calcular score de crédito simulado",
    operation_id="calculate_demo_credit_score",
    tags=["Score"],
    response_model=CreditScoreResponse,
    dependencies=[Depends(verify_api_key)],
)
def calculate_demo_credit_score(
    customer_id: str = Path(..., examples=["DEMO-001"]),
) -> CreditScoreResponse:
    """
    Calcula el score de crédito simulado para el cliente indicado.

    El score va de 300 a 850 y es exclusivamente demostrativo.
    Si los datos son insuficientes (ingresos == 0), retorna `status=insufficient_data`.
    Si el cliente no existe, retorna `status=not_found`.
    """
    return CreditScoreResponse(**calculate_credit_score(customer_id))


@app.post(
    "/api/fraud/check",
    summary="Verificar señales de posible fraude",
    operation_id="check_demo_fraud_signals",
    tags=["Fraude"],
    response_model=FraudSignalResponse,
    dependencies=[Depends(verify_api_key)],
)
def check_demo_fraud_signals(body: FraudCheckRequest) -> FraudSignalResponse:
    """
    Evalúa señales de alerta sobre una solicitud entrante.

    Aplica tres reglas deterministas sobre el historial sintético:
    - **R1**: Múltiples solicitudes del mismo cliente en los últimos 60 minutos.
      El tiempo de referencia es el timestamp más reciente en el historial del
      cliente (determinista con datos sintéticos).
    - **R2**: El `device_id` proporcionado está asociado a múltiples clientes en
      el historial. Usar el device_id real del dispositivo del solicitante.
    - **R3**: El monto supera 5× los ingresos mensuales del cliente.

    Una alerta **NO** constituye prueba de fraude.
    """
    return FraudSignalResponse(**check_fraud_signals(body.customer_id, body.amount, body.device_id))


@app.post(
    "/api/loans/evaluate",
    summary="Evaluar solicitud de crédito",
    operation_id="evaluate_demo_loan_application",
    tags=["Crédito"],
    response_model=LoanEvaluationResponse,
    dependencies=[Depends(verify_api_key)],
)
def evaluate_demo_loan_application(body: LoanEvaluationRequest) -> LoanEvaluationResponse:
    """
    Evalúa una solicitud de crédito combinando scoring, simulación de cuota y señales de fraude.

    ### Prioridad de decisión

    | Prioridad | Código          | Condición                                                   |
    |-----------|-----------------|-------------------------------------------------------------|
    | 1         | `NOT_FOUND`     | El customer_id no existe en los datos demo.                 |
    | 2         | `INSUF_DATA`    | Ingresos == 0; no se puede calcular score ni cuota.         |
    | 3         | `REJECTED`      | Score < 500 **o** carga > 60 %. **El rechazo crediticio tiene prioridad sobre cualquier alerta de fraude.** Si la solicitud es rechazada por criterios crediticios, la decisión es `rejected` aunque haya alerta HIGH. La alerta sigue visible en `fraud_check`. |
    | 4         | `REVIEW_FRAUD_ALERT` | Aprobada crediticiamente pero alerta HIGH de fraude.   |
    | 5         | `REVIEW`        | Score 500–649 o carga 40–60 %.                              |
    | 6         | `APPROVED`      | Score >= 650, carga <= 40 %, sin alerta HIGH.               |

    ### device_id

    Este endpoint no recibe `device_id`. La verificación interna de fraude usa
    `"WEB-PORTAL"` como identificador genérico del canal web. Para evaluar fraude
    con el device_id real del dispositivo del solicitante, llama primero a
    `POST /api/fraud/check` con el device_id correspondiente.

    No ejecuta desembolsos.
    """
    # Verificación de fraude con identificador genérico del canal web
    fraud_result = check_fraud_signals(body.customer_id, body.amount, "WEB-PORTAL")
    loan_result = evaluate_loan(body.customer_id, body.amount, body.term_months, body.annual_effective_rate)

    # Prioridad 3: el rechazo crediticio prevalece sobre la alerta de fraude.
    # Si ya es rejected, no escalamos a review_fraud_alert.
    # Solo escalamos cuando el crédito estaba aprobado (decision=approved).
    if loan_result["decision"] == "approved" and fraud_result["alert_level"] == "HIGH":
        loan_result["decision"] = "review_fraud_alert"
        loan_result["decision_code"] = "REVIEW_FRAUD_ALERT"
        loan_result["reasons"].append(
            "Alerta de fraude de nivel ALTO detectada. Solicitud derivada a revisión automática. "
            "No implica culpabilidad del cliente."
        )

    # fraud_check siempre presente cuando hay datos suficientes
    if loan_result.get("loan_simulation") is not None or loan_result["decision"] in (
        "approved", "rejected", "review", "review_fraud_alert"
    ):
        loan_result["fraud_check"] = fraud_result
    else:
        loan_result["fraud_check"] = None

    return LoanEvaluationResponse(**loan_result)


# ---------------------------------------------------------------------------
# Interfaz HTML
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Banco Demo — Créditos y Fraude</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif; background: #f7f8fa; color: #1f2328; font-size: 15px; line-height: 1.6; }
  .banner { background: #7c1d1d; color: #fff; text-align: center; padding: 10px 16px; font-size: 13px; font-weight: 600; letter-spacing: .3px; }
  header { background: #1f2328; color: #fff; padding: 18px 24px; }
  header h1 { font-size: 1.3rem; font-weight: 700; }
  header p { font-size: 13px; color: #9ca3af; margin-top: 2px; }
  .container { max-width: 900px; margin: 24px auto; padding: 0 16px 40px; }
  section { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 20px; margin-bottom: 20px; }
  section h2 { font-size: 1rem; font-weight: 700; margin-bottom: 14px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }
  label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; color: #57606a; }
  select, input[type=number] { width: 100%; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 14px; margin-bottom: 12px; background: #fff; }
  button { background: #3b82d4; color: #fff; border: none; padding: 9px 22px; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; }
  button:hover { background: #2563b5; }
  .row { display: flex; gap: 16px; flex-wrap: wrap; }
  .row .field { flex: 1; min-width: 160px; }
  pre { background: #f7f8fa; border: 1px solid #e5e7eb; border-radius: 4px; padding: 14px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 700; text-transform: uppercase; }
  .badge-approved    { background: #d1fae5; color: #065f46; }
  .badge-rejected    { background: #fee2e2; color: #991b1b; }
  .badge-review      { background: #fef3c7; color: #92400e; }
  .badge-review_fraud_alert { background: #fef3c7; color: #92400e; }
  .badge-insufficient_data, .badge-not_found { background: #e5e7eb; color: #374151; }
  .badge-HIGH   { background: #fee2e2; color: #991b1b; }
  .badge-MEDIUM { background: #fef3c7; color: #92400e; }
  .badge-LOW    { background: #d1fae5; color: #065f46; }
  .kv { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; margin-top: 8px; }
  .kv span { font-size: 13px; } .kv span b { color: #57606a; font-weight: 600; }
  .error { color: #991b1b; font-size: 13px; margin-top: 6px; }
  footer { text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; padding: 16px; margin-top: 8px; }
</style>
</head>
<body>
<div class="banner">⚠️ DEMOSTRACIÓN CON DATOS SINTÉTICOS. NO UTILIZAR PARA DECISIONES CREDITICIAS REALES.</div>
<header>
  <h1>Banco Demo — Créditos y Fraude</h1>
  <p>Prototipo con datos sintéticos reproducibles. Sin conexión a burós ni servicios externos.</p>
</header>
<div class="container">

  <!-- Selección de cliente -->
  <section>
    <h2>1. Seleccionar cliente</h2>
    <label for="clientSelect">Cliente demo</label>
    <select id="clientSelect"><option value="">-- selecciona --</option></select>
    <button onclick="loadProfile()">Ver perfil</button>
    <div id="profileResult" style="margin-top:14px"></div>
  </section>

  <!-- Solicitud de crédito -->
  <section>
    <h2>2. Evaluar solicitud de crédito</h2>
    <div class="row">
      <div class="field">
        <label for="loanAmount">Monto (COP)</label>
        <input type="number" id="loanAmount" placeholder="Ej. 20000000" min="1" step="100000">
      </div>
      <div class="field">
        <label for="loanTerm">Plazo (meses)</label>
        <input type="number" id="loanTerm" placeholder="Ej. 36" min="1" max="360">
      </div>
      <div class="field">
        <label for="loanRate">Tasa EA (decimal, ej. 0.18)</label>
        <input type="number" id="loanRate" placeholder="0.18" min="0.001" max="1.999" step="0.001">
      </div>
    </div>
    <button onclick="evaluateLoan()">Evaluar solicitud</button>
    <div id="loanResult" style="margin-top:14px"></div>
  </section>

</div>
<footer>Demostración con datos sintéticos · Banco Demo v1.1.0 · Hecho con IBM Bob</footer>

<script>
const fmt = n => new Intl.NumberFormat('es-CO', {style:'currency',currency:'COP',maximumFractionDigits:0}).format(n);
const pct = n => (n*100).toFixed(2) + '%';

async function loadCustomers() {
  const r = await fetch('/api/customers');
  const d = await r.json();
  const sel = document.getElementById('clientSelect');
  d.customers.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.id + ' — ingresos: ' + fmt(c.monthly_income);
    sel.appendChild(opt);
  });
}

const DECISION_LABELS = {
  approved: 'Aprobado',
  rejected: 'Rechazado',
  review: 'Revisión requerida',
  review_fraud_alert: 'Revisión — Alerta de fraude',
  insufficient_data: 'Datos insuficientes',
  not_found: 'Cliente no encontrado'
};

function badgeDecision(dec) {
  return `<span class="badge badge-${dec}">${DECISION_LABELS[dec] || dec}</span>`;
}

function badgeAlert(level) {
  const labels = {HIGH:'ALTO', MEDIUM:'MEDIO', LOW:'BAJO'};
  return `<span class="badge badge-${level}">${labels[level]||level}</span>`;
}

async function loadProfile() {
  const id = document.getElementById('clientSelect').value;
  if (!id) { document.getElementById('profileResult').innerHTML = '<p class="error">Selecciona un cliente.</p>'; return; }
  const [pr, sr] = await Promise.all([
    fetch('/api/customers/' + id + '/profile').then(r => r.json()),
    fetch('/api/customers/' + id + '/score').then(r => r.json())
  ]);
  const c = pr.customer;
  let html = `<div class="kv">
    <span><b>ID:</b> ${c.id}</span>
    <span><b>Ingresos mensuales:</b> ${fmt(c.monthly_income)}</span>
    <span><b>Obligaciones mensuales:</b> ${fmt(c.monthly_obligations)}</span>
    <span><b>Utilización crédito:</b> ${pct(c.credit_utilization)}</span>
    <span><b>Días de mora:</b> ${c.days_overdue}</span>
    <span><b>Antigüedad historial:</b> ${c.history_months} meses</span>
  </div>`;
  if (sr.status === 'ok') {
    html += `<div style="margin-top:10px"><b>Score simulado:</b> <span style="font-size:1.2rem;font-weight:700;color:#3b82d4">${sr.score}</span> / 850 &nbsp;<small style="color:#57606a">(${sr.rules_version})</small></div>`;
    const br = sr.breakdown;
    html += `<div class="kv" style="margin-top:6px;font-size:12px">
      <span><b>DTI:</b> ${pct(br.dti_ratio)}</span>
      <span><b>Parcial DTI:</b> ${br.partial_dti}</span>
      <span><b>Parcial utilización:</b> ${br.partial_utilization}</span>
      <span><b>Parcial mora:</b> ${br.partial_overdue}</span>
      <span><b>Parcial historial:</b> ${br.partial_history}</span>
    </div>`;
  } else if (sr.status === 'insufficient_data') {
    html += `<div style="margin-top:8px;color:#92400e"><b>Score:</b> Datos insuficientes — ${sr.reason||''}</div>`;
  } else {
    html += `<div style="margin-top:8px;color:#991b1b"><b>Score:</b> Cliente no encontrado.</div>`;
  }
  if (pr.request_history && pr.request_history.length) {
    html += `<div style="margin-top:10px"><b>Historial de solicitudes (${pr.request_history.length}):</b></div>`;
    html += '<pre>' + JSON.stringify(pr.request_history, null, 2) + '</pre>';
  }
  document.getElementById('profileResult').innerHTML = html;
}

async function evaluateLoan() {
  const id = document.getElementById('clientSelect').value;
  const amount = parseFloat(document.getElementById('loanAmount').value);
  const term = parseInt(document.getElementById('loanTerm').value);
  const rate = parseFloat(document.getElementById('loanRate').value);
  const el = document.getElementById('loanResult');
  if (!id) { el.innerHTML = '<p class="error">Selecciona un cliente.</p>'; return; }
  if (!amount || !term || !rate) { el.innerHTML = '<p class="error">Completa todos los campos.</p>'; return; }
  const resp = await fetch('/api/loans/evaluate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({customer_id: id, amount, term_months: term, annual_effective_rate: rate})
  });
  const d = await resp.json();

  let html = `<div style="margin-bottom:8px"><b>Decisión final:</b> ${badgeDecision(d.decision)}</div>`;
  if (d.reasons && d.reasons.length) {
    html += `<ul style="font-size:13px;padding-left:18px;margin-bottom:8px">${d.reasons.map(r=>'<li>'+r+'</li>').join('')}</ul>`;
  }

  if (d.loan_simulation) {
    const s = d.loan_simulation;
    html += `<div class="kv" style="margin-top:8px">
      <span><b>Cuota mensual estimada:</b> ${fmt(s.fixed_payment_cop)}</span>
      <span><b>Total a pagar:</b> ${fmt(s.total_payment_cop)}</span>
      <span><b>Tasa mensual:</b> ${(s.monthly_rate*100).toFixed(4)}%</span>
      <span><b>Carga financiera:</b> ${pct(s.new_debt_to_income)}</span>
    </div>`;
  }

  if (d.fraud_check) {
    const f = d.fraud_check;
    html += `<div style="margin-top:12px"><b>Nivel de alerta de fraude:</b> ${badgeAlert(f.alert_level)}</div>`;
    html += `<div style="font-size:13px;margin-top:4px">${f.recommendation}</div>`;
    if (f.signals && f.signals.length) {
      html += `<ul style="font-size:12px;padding-left:18px;color:#57606a;margin-top:4px">`;
      f.signals.forEach(s => { html += `<li><b>${s.rule_name}:</b> ${s.detail}</li>`; });
      html += '</ul>';
    }
    html += `<div style="font-size:11px;color:#9ca3af;margin-top:4px">${f.disclaimer}</div>`;
  }

  if (d.disclaimer) {
    html += `<p style="font-size:11px;color:#9ca3af;margin-top:10px">${d.disclaimer}</p>`;
  }

  el.innerHTML = html;
}

loadCustomers();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui() -> HTMLResponse:
    return HTMLResponse(content=_HTML)
