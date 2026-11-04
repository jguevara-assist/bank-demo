"""
main.py — Servicio FastAPI: Banco Demo — Créditos y Fraude.

Endpoints:
  GET  /api/customers                         → list_demo_customers
  GET  /api/customers/{customer_id}/profile   → get_customer_credit_profile
  GET  /api/customers/{customer_id}/score     → calculate_demo_credit_score
  POST /api/fraud/check                       → check_demo_fraud_signals
  POST /api/loans/evaluate                    → evaluate_demo_loan_application
  GET  /                                      → Interfaz HTML
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from core import (
    _CUSTOMERS,
    _CUSTOMER_INDEX,
    _REQUESTS,
    calculate_credit_score,
    check_fraud_signals,
    evaluate_loan,
)

# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Banco Demo — Créditos y Fraude",
    description=(
        "API de demostración con datos sintéticos. "
        "**No utilizar para decisiones crediticias reales.**"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------


class FraudCheckRequest(BaseModel):
    customer_id: str = Field(..., example="DEMO-001")
    amount: float = Field(..., gt=0, example=15000000)
    device_id: str = Field(..., example="DEV-AAA")


class LoanEvaluationRequest(BaseModel):
    customer_id: str = Field(..., example="DEMO-001")
    amount: float = Field(..., gt=0, example=20000000)
    term_months: int = Field(..., ge=1, le=360, example=36)
    annual_effective_rate: float = Field(
        ..., gt=0, lt=2.0, example=0.18,
        description="Tasa efectiva anual en formato decimal (ej. 0.18 = 18%).",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get(
    "/api/customers",
    summary="Listar clientes de demostración",
    operation_id="list_demo_customers",
    tags=["Clientes"],
)
def list_demo_customers() -> dict[str, Any]:
    """Retorna la lista de los 12 clientes sintéticos con sus datos financieros."""
    return {
        "total": len(_CUSTOMERS),
        "customers": _CUSTOMERS,
        "disclaimer": "Datos sintéticos. No representan personas reales.",
    }


@app.get(
    "/api/customers/{customer_id}/profile",
    summary="Perfil crediticio del cliente",
    operation_id="get_customer_credit_profile",
    tags=["Clientes"],
)
def get_customer_credit_profile(
    customer_id: str = Path(..., examples=["DEMO-001"]),
) -> dict[str, Any]:
    """Devuelve los datos financieros del cliente y el historial de solicitudes previas."""
    customer = _CUSTOMER_INDEX.get(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Cliente '{customer_id}' no encontrado.")

    history = [r for r in _REQUESTS if r["customer_id"] == customer_id]

    return {
        "customer": customer,
        "request_history": history,
        "disclaimer": "Datos sintéticos. No representan personas reales.",
    }


@app.get(
    "/api/customers/{customer_id}/score",
    summary="Calcular score de crédito simulado",
    operation_id="calculate_demo_credit_score",
    tags=["Score"],
)
def calculate_demo_credit_score(
    customer_id: str = Path(..., examples=["DEMO-001"]),
) -> dict[str, Any]:
    """
    Calcula el score de crédito simulado para el cliente indicado.

    El score va de 300 a 850 y es exclusivamente demostrativo.
    Si los datos son insuficientes (ingresos == 0), retorna estado `insufficient_data`.
    """
    return calculate_credit_score(customer_id)


@app.post(
    "/api/fraud/check",
    summary="Verificar señales de posible fraude",
    operation_id="check_demo_fraud_signals",
    tags=["Fraude"],
)
def check_demo_fraud_signals(body: FraudCheckRequest) -> dict[str, Any]:
    """
    Evalúa señales de alerta sobre una solicitud entrante.

    Aplica tres reglas deterministas sobre el historial sintético:
    - R1: Múltiples solicitudes en ventana de 60 minutos.
    - R2: Dispositivo asociado a varios clientes.
    - R3: Monto superior a 5× los ingresos mensuales.

    Una alerta NO constituye prueba de fraude.
    """
    return check_fraud_signals(body.customer_id, body.amount, body.device_id)


@app.post(
    "/api/loans/evaluate",
    summary="Evaluar solicitud de crédito",
    operation_id="evaluate_demo_loan_application",
    tags=["Crédito"],
)
def evaluate_demo_loan_application(body: LoanEvaluationRequest) -> dict[str, Any]:
    """
    Evalúa una solicitud de crédito combinando scoring, simulación de cuota y señales de fraude.

    Posibles decisiones:
    - `approved`           : score >= 650 y carga financiera <= 40%.
    - `rejected`           : score < 500 o carga > 60%.
    - `review`             : rango intermedio.
    - `review_fraud_alert` : la evaluación crediticia pasa pero hay alerta de fraude HIGH.
    - `insufficient_data`  : no hay datos suficientes del cliente.
    - `not_found`          : cliente no existe.

    No ejecuta desembolsos.
    """
    # Detección de fraude con dispositivo genérico cuando no se provee
    fraud = check_fraud_signals(body.customer_id, body.amount, "WEB-PORTAL")
    loan = evaluate_loan(body.customer_id, body.amount, body.term_months, body.annual_effective_rate)

    # Si la evaluación crediticia es aprobada pero hay alerta HIGH de fraude → revisión
    if loan["decision"] == "approved" and fraud["alert_level"] == "HIGH":
        loan["decision"] = "review_fraud_alert"
        loan["decision_code"] = "REVIEW_FRAUD_ALERT"
        loan["reasons"].append(
            "Alerta de fraude de nivel ALTO detectada. Solicitud derivada a revisión automática. "
            "No implica culpabilidad del cliente."
        )

    loan["fraud_check"] = fraud
    return loan


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
  .badge-review, .badge-review_fraud_alert { background: #fef3c7; color: #92400e; }
  .badge-insufficient_data, .badge-not_found { background: #e5e7eb; color: #374151; }
  .badge-HIGH    { background: #fee2e2; color: #991b1b; }
  .badge-MEDIUM  { background: #fef3c7; color: #92400e; }
  .badge-LOW     { background: #d1fae5; color: #065f46; }
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
<footer>Demostración con datos sintéticos · Banco Demo v1.0.0 · Hecho con IBM Bob</footer>

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

function badgeDecision(dec) {
  const labels = {approved:'Aprobado', rejected:'Rechazado', review:'Revisión', review_fraud_alert:'Revisión (Alerta Fraude)', insufficient_data:'Datos insuficientes', not_found:'No encontrado'};
  return `<span class="badge badge-${dec}">${labels[dec]||dec}</span>`;
}

function badgeAlert(level) {
  return `<span class="badge badge-${level}">${level}</span>`;
}

async function loadProfile() {
  const id = document.getElementById('clientSelect').value;
  if (!id) { document.getElementById('profileResult').innerHTML = '<p class="error">Selecciona un cliente.</p>'; return; }
  const r = await fetch('/api/customers/' + id + '/profile');
  const d = await r.json();
  const sr = await fetch('/api/customers/' + id + '/score');
  const sd = await sr.json();
  const c = d.customer;
  let html = `<div class="kv">
    <span><b>ID:</b> ${c.id}</span>
    <span><b>Ingresos mensuales:</b> ${fmt(c.monthly_income)}</span>
    <span><b>Obligaciones mensuales:</b> ${fmt(c.monthly_obligations)}</span>
    <span><b>Utilización crédito:</b> ${pct(c.credit_utilization)}</span>
    <span><b>Días de mora:</b> ${c.days_overdue}</span>
    <span><b>Antigüedad historial:</b> ${c.history_months} meses</span>
  </div>`;
  if (sd.status === 'ok') {
    html += `<div style="margin-top:10px"><b>Score simulado:</b> <span style="font-size:1.2rem;font-weight:700;color:#3b82d4">${sd.score}</span> / 850 &nbsp; <small style="color:#57606a">(${sd.rules_version})</small></div>`;
    const br = sd.breakdown;
    html += `<div class="kv" style="margin-top:6px;font-size:12px">
      <span><b>DTI:</b> ${pct(br.dti_ratio)}</span>
      <span><b>Parcial DTI:</b> ${br.partial_dti}</span>
      <span><b>Parcial utilización:</b> ${br.partial_utilization}</span>
      <span><b>Parcial mora:</b> ${br.partial_overdue}</span>
      <span><b>Parcial historial:</b> ${br.partial_history}</span>
    </div>`;
  } else {
    html += `<div style="margin-top:8px;color:#92400e"><b>Score:</b> Información insuficiente — ${sd.reason||''}</div>`;
  }
  if (d.request_history.length) {
    html += `<div style="margin-top:10px"><b>Historial de solicitudes (${d.request_history.length}):</b></div>`;
    html += '<pre>' + JSON.stringify(d.request_history, null, 2) + '</pre>';
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
  const body = {customer_id: id, amount, term_months: term, annual_effective_rate: rate};
  const r = await fetch('/api/loans/evaluate', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const d = await r.json();
  let html = `<div style="margin-bottom:8px"><b>Decisión:</b> ${badgeDecision(d.decision)}</div>`;
  if (d.reasons) html += `<ul style="font-size:13px;padding-left:18px">${d.reasons.map(r=>'<li>'+r+'</li>').join('')}</ul>`;
  if (d.loan_simulation) {
    const s = d.loan_simulation;
    html += `<div class="kv" style="margin-top:10px">
      <span><b>Cuota mensual estimada:</b> ${fmt(s.fixed_payment_cop)}</span>
      <span><b>Total a pagar:</b> ${fmt(s.total_payment_cop)}</span>
      <span><b>Tasa mensual:</b> ${(s.monthly_rate*100).toFixed(4)}%</span>
      <span><b>Carga financiera nueva:</b> ${pct(s.new_debt_to_income)}</span>
    </div>`;
  }
  if (d.fraud_check) {
    const f = d.fraud_check;
    html += `<div style="margin-top:12px"><b>Alerta de fraude:</b> ${badgeAlert(f.alert_level)} &nbsp;<span style="font-size:13px">${f.recommendation}</span></div>`;
    if (f.signals.length) {
      html += `<ul style="font-size:12px;padding-left:18px;color:#57606a">${f.signals.map(s=>'<li><b>'+s.rule_name+':</b> '+s.detail+'</li>').join('')}</ul>`;
    }
  }
  html += `<p style="font-size:11px;color:#9ca3af;margin-top:10px">${d.disclaimer||''}</p>`;
  el.innerHTML = html;
}

loadCustomers();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui() -> HTMLResponse:
    return HTMLResponse(content=_HTML)
