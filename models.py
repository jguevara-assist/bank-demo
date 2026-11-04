"""
models.py — Modelos Pydantic de entrada y salida del servicio Banco Demo.

Todos los modelos de respuesta reflejan exactamente los campos que devuelven
las funciones de core.py. Se usan como response_model en FastAPI para que
el esquema OpenAPI sea preciso y consumible por webMethods / MCP.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Modelos compartidos
# ---------------------------------------------------------------------------


class CustomerData(BaseModel):
    """Datos financieros de un cliente sintético."""

    id: str = Field(..., examples=["DEMO-001"], description="Identificador único del cliente demo.")
    monthly_income: float = Field(..., examples=[4500000], description="Ingresos mensuales en COP.")
    monthly_obligations: float = Field(..., examples=[800000], description="Obligaciones mensuales vigentes en COP.")
    history_months: int = Field(..., examples=[84], description="Antigüedad del historial crediticio en meses.")
    credit_utilization: float = Field(..., examples=[0.35], description="Proporción de crédito utilizado (0–1).")
    days_overdue: int = Field(..., examples=[0], description="Días de mora actuales.")


class RequestHistoryItem(BaseModel):
    """Entrada del historial de solicitudes sintéticas."""

    request_id: str = Field(..., examples=["REQ-001"])
    customer_id: str = Field(..., examples=["DEMO-001"])
    amount: float = Field(..., examples=[15000000])
    timestamp: str = Field(..., examples=["2026-10-01T09:10:00"])
    device_id: str = Field(..., examples=["DEV-AAA"])
    result: str = Field(..., examples=["approved"])


# ---------------------------------------------------------------------------
# 1. list_demo_customers → CustomerListResponse
# ---------------------------------------------------------------------------


class CustomerListResponse(BaseModel):
    """Respuesta de GET /api/customers."""

    total: int = Field(..., examples=[12])
    customers: List[CustomerData]
    disclaimer: str = Field(
        ...,
        examples=["Datos sintéticos. No representan personas reales."],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total": 12,
                    "customers": [
                        {
                            "id": "DEMO-001",
                            "monthly_income": 4500000,
                            "monthly_obligations": 800000,
                            "history_months": 84,
                            "credit_utilization": 0.35,
                            "days_overdue": 0,
                        }
                    ],
                    "disclaimer": "Datos sintéticos. No representan personas reales.",
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# 2. get_customer_credit_profile → CustomerProfileResponse
# ---------------------------------------------------------------------------


class CustomerProfileResponse(BaseModel):
    """Respuesta de GET /api/customers/{customer_id}/profile."""

    customer: CustomerData
    request_history: List[RequestHistoryItem]
    disclaimer: str = Field(..., examples=["Datos sintéticos. No representan personas reales."])

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "customer": {
                        "id": "DEMO-001",
                        "monthly_income": 4500000,
                        "monthly_obligations": 800000,
                        "history_months": 84,
                        "credit_utilization": 0.35,
                        "days_overdue": 0,
                    },
                    "request_history": [
                        {
                            "request_id": "REQ-001",
                            "customer_id": "DEMO-001",
                            "amount": 15000000,
                            "timestamp": "2026-10-01T09:10:00",
                            "device_id": "DEV-AAA",
                            "result": "approved",
                        }
                    ],
                    "disclaimer": "Datos sintéticos. No representan personas reales.",
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# 3. calculate_demo_credit_score → CreditScoreResponse
# ---------------------------------------------------------------------------


class ScoreWeights(BaseModel):
    dti: float = Field(..., examples=[0.35])
    utilization: float = Field(..., examples=[0.30])
    overdue: float = Field(..., examples=[0.25])
    history: float = Field(..., examples=[0.10])


class ScoreBreakdown(BaseModel):
    """Desglose de factores del score de crédito."""

    dti_ratio: float = Field(..., description="Relación obligaciones / ingresos.", examples=[0.1778])
    partial_dti: float = Field(..., description="Puntuación parcial DTI (0–1, 1=mejor).", examples=[0.8222])
    partial_utilization: float = Field(..., description="Puntuación parcial utilización (0–1).", examples=[0.65])
    partial_overdue: float = Field(..., description="Puntuación parcial mora (1.0 / 0.5 / 0.25 / 0.0).", examples=[1.0])
    partial_history: float = Field(..., description="Puntuación parcial antigüedad (0–1).", examples=[0.7])
    composite: float = Field(..., description="Puntuación compuesta ponderada (0–1).", examples=[0.7928])
    weights: ScoreWeights


class CreditScoreResponse(BaseModel):
    """
    Respuesta de GET /api/customers/{customer_id}/score.

    `status` posibles:
    - `ok`                : score calculado correctamente.
    - `insufficient_data` : ingresos == 0; score no disponible.
    - `not_found`         : cliente no existe en los datos demo.
    """

    customer_id: str = Field(..., examples=["DEMO-001"])
    status: Literal["ok", "insufficient_data", "not_found"]
    score: Optional[int] = Field(
        None,
        ge=300,
        le=850,
        description="Score simulado (300–850). Null cuando status != ok.",
        examples=[736],
    )
    breakdown: Optional[ScoreBreakdown] = Field(
        None, description="Desglose de factores. Null cuando status != ok."
    )
    rules_version: str = Field(..., examples=["v1.0"])
    reason: Optional[str] = Field(
        None,
        description="Motivo de datos insuficientes. Solo presente cuando status=insufficient_data.",
        examples=["Ingresos iguales a cero o no informados."],
    )
    disclaimer: Optional[str] = Field(
        None,
        examples=["Score exclusivamente demostrativo. No representa buró de crédito ni modelo validado."],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "customer_id": "DEMO-003",
                    "status": "ok",
                    "score": 791,
                    "breakdown": {
                        "dti_ratio": 0.1463,
                        "partial_dti": 0.8537,
                        "partial_utilization": 0.8,
                        "partial_overdue": 1.0,
                        "partial_history": 1.0,
                        "composite": 0.893,
                        "weights": {"dti": 0.35, "utilization": 0.30, "overdue": 0.25, "history": 0.10},
                    },
                    "rules_version": "v1.0",
                    "disclaimer": "Score exclusivamente demostrativo. No representa buró de crédito ni modelo validado.",
                },
                {
                    "customer_id": "DEMO-012",
                    "status": "insufficient_data",
                    "score": None,
                    "breakdown": None,
                    "rules_version": "v1.0",
                    "reason": "Ingresos iguales a cero o no informados.",
                },
            ]
        }
    }


# ---------------------------------------------------------------------------
# 4. check_demo_fraud_signals → FraudSignalResponse
# ---------------------------------------------------------------------------


class FraudSignal(BaseModel):
    rule_id: str = Field(..., examples=["R1"])
    rule_name: str = Field(..., examples=["MULTIPLE_REQUESTS"])
    detail: str = Field(
        ...,
        examples=["Se detectaron 2 solicitudes previas del cliente en los últimos 60 minutos."],
    )


class FraudSignalResponse(BaseModel):
    """
    Respuesta de POST /api/fraud/check.

    `alert_level`:
    - `HIGH`   : ≥2 reglas activas → revisión automática.
    - `MEDIUM` : 1 regla activa.
    - `LOW`    : ninguna regla activa.

    Una alerta NO constituye prueba de fraude ni implica culpabilidad del cliente.
    """

    customer_id: str = Field(..., examples=["DEMO-001"])
    device_id: str = Field(..., examples=["DEV-AAA"])
    amount: float = Field(..., examples=[15000000])
    alert_level: Literal["HIGH", "MEDIUM", "LOW"]
    signals_count: int = Field(..., ge=0, examples=[2])
    signals: List[FraudSignal]
    recommendation: str = Field(
        ...,
        examples=["Solicitud enviada a revisión automática por múltiples señales. No implica culpabilidad del cliente."],
    )
    rules_version: str = Field(..., examples=["v1.0"])
    disclaimer: str = Field(
        ...,
        examples=["Las alertas son indicativas. No constituyen evidencia de fraude ni implican culpabilidad."],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "customer_id": "DEMO-001",
                    "device_id": "DEV-AAA",
                    "amount": 25000000,
                    "alert_level": "HIGH",
                    "signals_count": 2,
                    "signals": [
                        {
                            "rule_id": "R1",
                            "rule_name": "MULTIPLE_REQUESTS",
                            "detail": "Se detectaron 3 solicitudes previas en los últimos 60 minutos.",
                        },
                        {
                            "rule_id": "R3",
                            "rule_name": "UNUSUAL_AMOUNT",
                            "detail": "El monto solicitado (25,000,000 COP) supera 5× los ingresos mensuales.",
                        },
                    ],
                    "recommendation": "Solicitud enviada a revisión automática por múltiples señales. No implica culpabilidad del cliente.",
                    "rules_version": "v1.0",
                    "disclaimer": "Las alertas son indicativas. No constituyen evidencia de fraude ni implican culpabilidad.",
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# 5. evaluate_demo_loan_application → LoanEvaluationResponse
# ---------------------------------------------------------------------------


class LoanSimulation(BaseModel):
    """Resultado de la simulación financiera."""

    amount_cop: float = Field(..., description="Monto solicitado en COP.", examples=[20000000])
    term_months: int = Field(..., description="Plazo en meses.", examples=[36])
    annual_effective_rate: float = Field(..., description="Tasa efectiva anual (decimal).", examples=[0.18])
    monthly_rate: float = Field(..., description="Tasa mensual calculada (decimal).", examples=[0.01388])
    fixed_payment_cop: float = Field(..., description="Cuota fija mensual estimada en COP.", examples=[723680.0])
    total_payment_cop: float = Field(..., description="Total a pagar al final del plazo en COP.", examples=[26052480.0])
    new_debt_to_income: float = Field(
        ...,
        description="Carga financiera resultante: (obligaciones actuales + nueva cuota) / ingresos.",
        examples=[0.3386],
    )


class ScoreSummary(BaseModel):
    score: Optional[int] = Field(None, examples=[736])
    status: Literal["ok", "insufficient_data", "not_found"]
    rules_version: str = Field(..., examples=["v1.0"])


class LoanEvaluationResponse(BaseModel):
    """
    Respuesta de POST /api/loans/evaluate.

    Prioridad de decisión (aplicada en este orden):
    1. `not_found`         — el customer_id no existe.
    2. `insufficient_data` — ingresos == 0; no se puede calcular score ni cuota.
    3. `rejected`          — score < 500 O carga financiera > 60%. El rechazo
                             crediticio tiene prioridad sobre cualquier alerta de fraude:
                             si la solicitud es rechazada por criterios crediticios,
                             la decisión final es `rejected` aunque haya alerta HIGH.
    4. `review_fraud_alert`— aprobada crediticiamente (score≥650, carga≤40%) pero
                             alerta de fraude HIGH. La decisión se eleva a revisión.
    5. `review`            — rango intermedio (score 500–649 o carga 40–60%).
    6. `approved`          — score ≥ 650 y carga ≤ 40% y sin alerta HIGH de fraude.

    El campo `fraud_check.device_id` muestra el dispositivo usado en la evaluación.
    Cuando se llama a este endpoint sin proveer device_id, se utiliza `"WEB-PORTAL"`
    como identificador genérico. Para una evaluación de fraude precisa, usa
    POST /api/fraud/check con el device_id real del dispositivo del solicitante.
    """

    customer_id: str = Field(..., examples=["DEMO-003"])
    decision: Literal[
        "approved",
        "rejected",
        "review",
        "review_fraud_alert",
        "insufficient_data",
        "not_found",
    ]
    decision_code: Literal[
        "APPROVED",
        "REJECTED",
        "REVIEW",
        "REVIEW_FRAUD_ALERT",
        "INSUF_DATA",
        "NOT_FOUND",
    ]
    reasons: List[str] = Field(
        ...,
        description="Lista de motivos que explican la decisión.",
        examples=[["Score 791 >= 650 y carga financiera 33.86% <= 40%."]],
    )
    loan_simulation: Optional[LoanSimulation] = Field(
        None,
        description="Simulación financiera. Null cuando status es not_found o insufficient_data.",
    )
    score_summary: ScoreSummary
    fraud_check: Optional[FraudSignalResponse] = Field(
        None,
        description=(
            "Resultado de la verificación de señales de fraude. "
            "device_id='WEB-PORTAL' cuando el solicitante no proveyó identificador de dispositivo. "
            "Null cuando status es not_found o insufficient_data."
        ),
    )
    rules_version: str = Field(..., examples=["v1.0"])
    disclaimer: str = Field(
        ...,
        examples=["Evaluación exclusivamente demostrativa. No constituye oferta crediticia ni compromiso de desembolso."],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Caso aprobado — DEMO-003",
                    "value": {
                        "customer_id": "DEMO-003",
                        "decision": "approved",
                        "decision_code": "APPROVED",
                        "reasons": ["Score 791 >= 650 y carga financiera 18.83% <= 40%."],
                        "loan_simulation": {
                            "amount_cop": 20000000,
                            "term_months": 36,
                            "annual_effective_rate": 0.18,
                            "monthly_rate": 0.01388,
                            "fixed_payment_cop": 723680.0,
                            "total_payment_cop": 26052480.0,
                            "new_debt_to_income": 0.2099,
                        },
                        "score_summary": {"score": 791, "status": "ok", "rules_version": "v1.0"},
                        "fraud_check": {
                            "customer_id": "DEMO-003",
                            "device_id": "WEB-PORTAL",
                            "amount": 20000000,
                            "alert_level": "LOW",
                            "signals_count": 0,
                            "signals": [],
                            "recommendation": "Sin señales de alerta detectadas.",
                            "rules_version": "v1.0",
                            "disclaimer": "Las alertas son indicativas. No constituyen evidencia de fraude ni implican culpabilidad.",
                        },
                        "rules_version": "v1.0",
                        "disclaimer": "Evaluación exclusivamente demostrativa. No constituye oferta crediticia ni compromiso de desembolso.",
                    },
                },
                {
                    "summary": "Caso rechazado — DEMO-010",
                    "value": {
                        "customer_id": "DEMO-010",
                        "decision": "rejected",
                        "decision_code": "REJECTED",
                        "reasons": [
                            "Score 300 inferior al mínimo requerido (500).",
                            "Carga financiera 95.38% supera el límite del 60%.",
                        ],
                        "loan_simulation": {
                            "amount_cop": 5000000,
                            "term_months": 24,
                            "annual_effective_rate": 0.18,
                            "monthly_rate": 0.01388,
                            "fixed_payment_cop": 254920.0,
                            "total_payment_cop": 6118080.0,
                            "new_debt_to_income": 0.9538,
                        },
                        "score_summary": {"score": 300, "status": "ok", "rules_version": "v1.0"},
                        "fraud_check": {
                            "customer_id": "DEMO-010",
                            "device_id": "WEB-PORTAL",
                            "amount": 5000000,
                            "alert_level": "LOW",
                            "signals_count": 0,
                            "signals": [],
                            "recommendation": "Sin señales de alerta detectadas.",
                            "rules_version": "v1.0",
                            "disclaimer": "Las alertas son indicativas. No constituyen evidencia de fraude ni implican culpabilidad.",
                        },
                        "rules_version": "v1.0",
                        "disclaimer": "Evaluación exclusivamente demostrativa. No constituye oferta crediticia ni compromiso de desembolso.",
                    },
                },
                {
                    "summary": "Caso revisión por alerta de fraude — DEMO-001",
                    "value": {
                        "customer_id": "DEMO-001",
                        "decision": "review_fraud_alert",
                        "decision_code": "REVIEW_FRAUD_ALERT",
                        "reasons": [
                            "Score 736 >= 650 y carga financiera 28.50% <= 40%.",
                            "Alerta de fraude de nivel ALTO detectada. Solicitud derivada a revisión automática. No implica culpabilidad del cliente.",
                        ],
                        "loan_simulation": {
                            "amount_cop": 25000000,
                            "term_months": 36,
                            "annual_effective_rate": 0.18,
                            "monthly_rate": 0.01388,
                            "fixed_payment_cop": 904600.0,
                            "total_payment_cop": 32565600.0,
                            "new_debt_to_income": 0.3788,
                        },
                        "score_summary": {"score": 736, "status": "ok", "rules_version": "v1.0"},
                        "fraud_check": {
                            "customer_id": "DEMO-001",
                            "device_id": "WEB-PORTAL",
                            "amount": 25000000,
                            "alert_level": "HIGH",
                            "signals_count": 2,
                            "signals": [
                                {"rule_id": "R1", "rule_name": "MULTIPLE_REQUESTS", "detail": "..."},
                                {"rule_id": "R3", "rule_name": "UNUSUAL_AMOUNT", "detail": "..."},
                            ],
                            "recommendation": "Solicitud enviada a revisión automática por múltiples señales.",
                            "rules_version": "v1.0",
                            "disclaimer": "Las alertas son indicativas.",
                        },
                        "rules_version": "v1.0",
                        "disclaimer": "Evaluación exclusivamente demostrativa. No constituye oferta crediticia ni compromiso de desembolso.",
                    },
                },
                {
                    "summary": "Caso datos insuficientes — DEMO-012",
                    "value": {
                        "customer_id": "DEMO-012",
                        "decision": "insufficient_data",
                        "decision_code": "INSUF_DATA",
                        "reasons": ["Ingresos iguales a cero o no informados."],
                        "loan_simulation": None,
                        "score_summary": {"score": None, "status": "insufficient_data", "rules_version": "v1.0"},
                        "fraud_check": None,
                        "rules_version": "v1.0",
                        "disclaimer": "Evaluación exclusivamente demostrativa. No constituye oferta crediticia ni compromiso de desembolso.",
                    },
                },
            ]
        }
    }


# ---------------------------------------------------------------------------
# Modelos de entrada (request) — también centralizados aquí
# ---------------------------------------------------------------------------


class FraudCheckRequest(BaseModel):
    """Cuerpo de POST /api/fraud/check."""

    customer_id: str = Field(
        ...,
        examples=["DEMO-001"],
        description="Identificador del cliente demo.",
    )
    amount: float = Field(
        ...,
        gt=0,
        examples=[15000000],
        description="Monto de la solicitud en COP.",
    )
    device_id: str = Field(
        ...,
        examples=["DEV-AAA"],
        description=(
            "Identificador del dispositivo desde el que se realiza la solicitud. "
            "Se usa para la regla R2 (dispositivo asociado a múltiples clientes). "
            "Debe ser el identificador real del dispositivo del solicitante."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "customer_id": "DEMO-001",
                    "amount": 15000000,
                    "device_id": "DEV-AAA",
                }
            ]
        }
    }


class LoanEvaluationRequest(BaseModel):
    """
    Cuerpo de POST /api/loans/evaluate.

    Nota sobre device_id: este endpoint no recibe device_id. La verificación
    de fraude interna utiliza `"WEB-PORTAL"` como identificador genérico del
    canal web, lo que significa que la regla R2 (dispositivo multicliente) solo
    se activará si el historial contiene solicitudes previas desde "WEB-PORTAL".
    Para una verificación de fraude con device_id real, usa POST /api/fraud/check.
    """

    customer_id: str = Field(..., examples=["DEMO-003"])
    amount: float = Field(..., gt=0, examples=[20000000], description="Monto en COP.")
    term_months: int = Field(..., ge=1, le=360, examples=[36], description="Plazo en meses (1–360).")
    annual_effective_rate: float = Field(
        ...,
        gt=0,
        lt=2.0,
        examples=[0.18],
        description="Tasa efectiva anual en formato decimal (ej. 0.18 = 18 %).",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"customer_id": "DEMO-003", "amount": 20000000, "term_months": 36, "annual_effective_rate": 0.18},
                {"customer_id": "DEMO-010", "amount": 5000000, "term_months": 24, "annual_effective_rate": 0.18},
                {"customer_id": "DEMO-012", "amount": 10000000, "term_months": 24, "annual_effective_rate": 0.18},
                {"customer_id": "DEMO-001", "amount": 25000000, "term_months": 36, "annual_effective_rate": 0.18},
            ]
        }
    }
