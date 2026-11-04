"""
core.py — Lógica de negocio del servicio Banco Demo — Créditos y Fraude.

Contiene:
  - Carga de datos sintéticos
  - Scoring de crédito determinista (v1.0)
  - Simulación de crédito (cuota fija)
  - Detección de señales de fraude

Reloj utilizado para R1 (ventana de solicitudes):
  La regla R1 compara timestamps del historial contra el timestamp de la
  solicitud más reciente registrada en _REQUESTS (no contra datetime.now()).
  Esto hace que el resultado sea determinista con los datos sintéticos y
  permite pruebas reproducibles sin manipular el reloj del sistema.

  Para pruebas que necesiten controlar la referencia temporal, pasa un
  callable `now_fn: () -> datetime` a check_fraud_signals. Por defecto
  se usa `_default_now`, que devuelve el máximo timestamp del historial
  del cliente (comportamiento original).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent / "data"


def _load_json(filename: str) -> list[dict]:
    with open(_DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


_CUSTOMERS: list[dict] = _load_json("customers.json")
_REQUESTS: list[dict] = _load_json("requests.json")

_CUSTOMER_INDEX: dict[str, dict] = {c["id"]: c for c in _CUSTOMERS}


# ---------------------------------------------------------------------------
# Scoring de crédito — versión v1.0
# ---------------------------------------------------------------------------
# Fórmula:
#   score = 300 + (W_DTI * P_dti + W_UTIL * P_util + W_MORA * P_mora + W_HIST * P_hist) * 550
#
# Ponderaciones:
#   W_DTI  = 0.35  (relación obligaciones / ingresos — menor es mejor)
#   W_UTIL = 0.30  (utilización de crédito     — menor es mejor)
#   W_MORA = 0.25  (días de mora               — menor es mejor)
#   W_HIST = 0.10  (antigüedad del historial   — mayor es mejor)
#
# Puntuaciones parciales (0 a 1, donde 1 = mejor perfil):
#   P_dti  = max(0, 1 - dti / 1.0)          dti >= 1.0 → 0
#   P_util = max(0, 1 - utilization / 1.0)
#   P_mora = 1 si mora=0, 0.5 si mora<=30,
#            0.25 si mora<=60, 0 si mora>60
#   P_hist = min(1, history_months / 120)    120 meses = máxima antigüedad esperada
#
# Si ingresos == 0 o faltan datos → "información insuficiente"

SCORE_RULES_VERSION = "v1.0"

WEIGHTS = {
    "dti": 0.35,
    "utilization": 0.30,
    "overdue": 0.25,
    "history": 0.10,
}


def _partial_dti(income: float, obligations: float) -> float:
    dti = obligations / income
    return max(0.0, 1.0 - dti / 1.0)


def _partial_util(utilization: float) -> float:
    return max(0.0, 1.0 - utilization)


def _partial_overdue(days: int) -> float:
    if days == 0:
        return 1.0
    if days <= 30:
        return 0.5
    if days <= 60:
        return 0.25
    return 0.0


def _partial_history(months: int) -> float:
    return min(1.0, months / 120.0)


def calculate_credit_score(customer_id: str) -> dict[str, Any]:
    customer = _CUSTOMER_INDEX.get(customer_id)
    if customer is None:
        return {
            "customer_id": customer_id,
            "status": "not_found",
            "score": None,
            "breakdown": None,
            "rules_version": SCORE_RULES_VERSION,
        }

    income = customer["monthly_income"]
    obligations = customer["monthly_obligations"]
    history = customer["history_months"]
    utilization = customer["credit_utilization"]
    overdue = customer["days_overdue"]

    # Datos insuficientes
    if income == 0:
        return {
            "customer_id": customer_id,
            "status": "insufficient_data",
            "score": None,
            "breakdown": None,
            "rules_version": SCORE_RULES_VERSION,
            "reason": "Ingresos iguales a cero o no informados.",
        }

    p_dti = _partial_dti(income, obligations)
    p_util = _partial_util(utilization)
    p_mora = _partial_overdue(overdue)
    p_hist = _partial_history(history)

    composite = (
        WEIGHTS["dti"] * p_dti
        + WEIGHTS["utilization"] * p_util
        + WEIGHTS["overdue"] * p_mora
        + WEIGHTS["history"] * p_hist
    )

    score = round(300 + composite * 550)

    breakdown = {
        "dti_ratio": round(obligations / income, 4),
        "partial_dti": round(p_dti, 4),
        "partial_utilization": round(p_util, 4),
        "partial_overdue": round(p_mora, 4),
        "partial_history": round(p_hist, 4),
        "composite": round(composite, 6),
        "weights": WEIGHTS,
    }

    return {
        "customer_id": customer_id,
        "status": "ok",
        "score": score,
        "breakdown": breakdown,
        "rules_version": SCORE_RULES_VERSION,
        "disclaimer": "Score exclusivamente demostrativo. No representa buró de crédito ni modelo validado.",
    }


# ---------------------------------------------------------------------------
# Simulación de crédito
# ---------------------------------------------------------------------------
# Conversión TEA → TM:  tm = (1 + tea)^(1/12) - 1
# Cuota fija (PMT):     C = P * tm / (1 - (1+tm)^-n)
#
# Reglas de decisión (documentadas):
#   APROBADO        : score >= 650 y nueva_carga <= 0.40
#   RECHAZADO       : score <  500  o nueva_carga >  0.60
#   REVISIÓN        : demás casos (score 500-649 o carga 0.40-0.60)
#   INSUF. DATOS    : score es None


LOAN_RULES_VERSION = "v1.0"


def _monthly_rate(annual_effective_rate: float) -> float:
    """Convierte tasa efectiva anual a tasa mensual."""
    return (1 + annual_effective_rate) ** (1 / 12) - 1


def _fixed_payment(principal: float, monthly_rate: float, months: int) -> float:
    """Calcula cuota fija (PMT)."""
    if monthly_rate == 0:
        return principal / months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** (-months))


def evaluate_loan(
    customer_id: str,
    amount: float,
    term_months: int,
    annual_effective_rate: float,
) -> dict[str, Any]:
    score_result = calculate_credit_score(customer_id)

    _LOAN_DISCLAIMER = "Evaluación exclusivamente demostrativa. No constituye oferta crediticia ni compromiso de desembolso."

    if score_result["status"] == "not_found":
        return {
            "customer_id": customer_id,
            "decision": "not_found",
            "decision_code": "NOT_FOUND",
            "reasons": ["Cliente no encontrado en la base de datos de demostración."],
            "loan_simulation": None,
            "score_summary": score_result,
            "rules_version": LOAN_RULES_VERSION,
            "disclaimer": _LOAN_DISCLAIMER,
        }

    if score_result["status"] == "insufficient_data":
        return {
            "customer_id": customer_id,
            "decision": "insufficient_data",
            "decision_code": "INSUF_DATA",
            "reasons": [score_result.get("reason", "Datos insuficientes.")],
            "loan_simulation": None,
            "score_summary": score_result,
            "rules_version": LOAN_RULES_VERSION,
            "disclaimer": _LOAN_DISCLAIMER,
        }

    customer = _CUSTOMER_INDEX[customer_id]
    income = customer["monthly_income"]
    current_obligations = customer["monthly_obligations"]
    score = score_result["score"]

    tm = _monthly_rate(annual_effective_rate)
    cuota = _fixed_payment(amount, tm, term_months)
    total_payment = round(cuota * term_months, 2)
    new_load_ratio = round((current_obligations + cuota) / income, 4)

    simulation = {
        "amount_cop": amount,
        "term_months": term_months,
        "annual_effective_rate": annual_effective_rate,
        "monthly_rate": round(tm, 8),
        "fixed_payment_cop": round(cuota, 2),
        "total_payment_cop": total_payment,
        "new_debt_to_income": new_load_ratio,
    }

    reasons = []

    # Clasificación
    if score >= 650 and new_load_ratio <= 0.40:
        decision = "approved"
        decision_code = "APPROVED"
        reasons.append(f"Score {score} >= 650 y carga financiera {new_load_ratio:.2%} <= 40%.")
    elif score < 500 or new_load_ratio > 0.60:
        decision = "rejected"
        decision_code = "REJECTED"
        if score < 500:
            reasons.append(f"Score {score} inferior al mínimo requerido (500).")
        if new_load_ratio > 0.60:
            reasons.append(
                f"Carga financiera {new_load_ratio:.2%} supera el límite del 60%."
            )
    else:
        decision = "review"
        decision_code = "REVIEW"
        reasons.append(
            f"Score {score} en rango intermedio (500-649) o carga {new_load_ratio:.2%} entre 40%-60%. "
            "Se requiere revisión manual."
        )

    return {
        "customer_id": customer_id,
        "decision": decision,
        "decision_code": decision_code,
        "reasons": reasons,
        "loan_simulation": simulation,
        "score_summary": {
            "score": score,
            "status": score_result["status"],
            "rules_version": score_result["rules_version"],
        },
        "rules_version": LOAN_RULES_VERSION,
        "disclaimer": "Evaluación exclusivamente demostrativa. No constituye oferta crediticia ni compromiso de desembolso.",
    }


# ---------------------------------------------------------------------------
# Detección de señales de fraude
# ---------------------------------------------------------------------------
# Reglas (documentadas):
#   R1 — MULTIPLE_REQUESTS  : >= 3 solicitudes del mismo cliente en menos de 60 minutos.
#   R2 — DEVICE_MULTI_CLIENT: un dispositivo asociado a >= 2 clientes distintos.
#   R3 — UNUSUAL_AMOUNT     : monto > 5× los ingresos mensuales del cliente.
#
# Niveles de alerta:
#   HIGH   : >= 2 reglas activas  → solicitud enviada a revisión automática
#   MEDIUM : 1 regla activa       → marcada para revisión
#   LOW    : 0 reglas activas     → sin señales detectadas
#
# Una alerta NO constituye prueba de fraude ni implica culpabilidad del cliente.

FRAUD_RULES_VERSION = "v1.0"
_RAPID_REQUEST_WINDOW_MINUTES = 60
_RAPID_REQUEST_MIN_COUNT = 3
_DEVICE_MULTI_CLIENT_MIN = 2
_UNUSUAL_AMOUNT_FACTOR = 5


def _default_now(customer_times: list[datetime]) -> datetime:
    """
    Reloj por defecto para R1.

    Devuelve el timestamp más reciente del historial del cliente, lo que hace
    que la ventana de 60 minutos sea determinista con los datos sintéticos y
    que las pruebas sean reproducibles sin depender de datetime.now().

    Razonamiento: en producción real se usaría datetime.now(). En esta demo
    se ancla al historial para garantizar que los casos de prueba no caduquen
    con el paso del tiempo.
    """
    return max(customer_times)


def check_fraud_signals(
    customer_id: str,
    amount: float,
    device_id: str,
    now_fn: Optional[Callable[[list[datetime]], datetime]] = None,
) -> dict[str, Any]:
    """
    Evalúa señales de posible fraude sobre una solicitud entrante.

    Parámetro `now_fn`:
      Callable que recibe la lista de timestamps del historial del cliente y
      devuelve el datetime de referencia para la ventana R1. Si es None, se
      usa `_default_now` (máximo del historial). Para pruebas con reloj fijo,
      pasa: `now_fn=lambda _: datetime(2026, 10, 1, 9, 20, 0)`.
    """
    if now_fn is None:
        now_fn = _default_now

    customer = _CUSTOMER_INDEX.get(customer_id)
    signals: list[dict] = []

    # R1 — Solicitudes rápidas
    customer_times: list[datetime] = []
    for req in _REQUESTS:
        if req["customer_id"] == customer_id:
            dt = datetime.fromisoformat(req["timestamp"])
            customer_times.append(dt)

    if customer_times:
        reference_time = now_fn(customer_times)
        window_start = reference_time - timedelta(minutes=_RAPID_REQUEST_WINDOW_MINUTES)
        recent = [t for t in customer_times if t >= window_start]
        # +1 para incluir la solicitud actual
        if len(recent) + 1 >= _RAPID_REQUEST_MIN_COUNT:
            signals.append({
                "rule_id": "R1",
                "rule_name": "MULTIPLE_REQUESTS",
                "detail": (
                    f"Se detectaron {len(recent)} solicitudes previas del cliente en los últimos "
                    f"{_RAPID_REQUEST_WINDOW_MINUTES} minutos. Con la solicitud actual, "
                    f"supera el umbral de {_RAPID_REQUEST_MIN_COUNT}."
                ),
            })

    # R2 — Dispositivo compartido entre clientes
    clients_on_device = {
        req["customer_id"]
        for req in _REQUESTS
        if req["device_id"] == device_id
    }
    # También contamos el cliente actual
    clients_on_device.add(customer_id)
    if len(clients_on_device) >= _DEVICE_MULTI_CLIENT_MIN:
        signals.append({
            "rule_id": "R2",
            "rule_name": "DEVICE_MULTI_CLIENT",
            "detail": (
                f"El dispositivo {device_id!r} está asociado a {len(clients_on_device)} clientes distintos "
                f"en el historial de solicitudes."
            ),
        })

    # R3 — Monto inusualmente alto
    if customer and customer["monthly_income"] > 0:
        threshold = customer["monthly_income"] * _UNUSUAL_AMOUNT_FACTOR
        if amount > threshold:
            signals.append({
                "rule_id": "R3",
                "rule_name": "UNUSUAL_AMOUNT",
                "detail": (
                    f"El monto solicitado ({amount:,.0f} COP) supera {_UNUSUAL_AMOUNT_FACTOR}× "
                    f"los ingresos mensuales ({customer['monthly_income']:,.0f} COP). "
                    f"Umbral: {threshold:,.0f} COP."
                ),
            })

    # Nivel de alerta
    n = len(signals)
    if n >= 2:
        alert_level = "HIGH"
        recommendation = "Solicitud enviada a revisión automática por múltiples señales. No implica culpabilidad del cliente."
    elif n == 1:
        alert_level = "MEDIUM"
        recommendation = "Señal detectada. Se recomienda revisión adicional."
    else:
        alert_level = "LOW"
        recommendation = "Sin señales de alerta detectadas."

    return {
        "customer_id": customer_id,
        "device_id": device_id,
        "amount": amount,
        "alert_level": alert_level,
        "signals_count": n,
        "signals": signals,
        "recommendation": recommendation,
        "rules_version": FRAUD_RULES_VERSION,
        "disclaimer": "Las alertas son indicativas. No constituyen evidencia de fraude ni implican culpabilidad.",
    }
