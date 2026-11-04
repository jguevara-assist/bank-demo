"""
tests/test_core.py — Pruebas esenciales de lógica de negocio.

Cubre:
  - Cálculo determinista de cuota fija.
  - Score correcto para clientes representativos.
  - Estado insufficient_data para DEMO-012 (ingresos == 0).
  - Alerta HIGH para DEMO-001 (múltiples solicitudes + dispositivo compartido).
"""

import sys
import math
from pathlib import Path

# Asegurar que el módulo core sea importable desde tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import (
    _fixed_payment,
    _monthly_rate,
    calculate_credit_score,
    check_fraud_signals,
    evaluate_loan,
    SCORE_RULES_VERSION,
    LOAN_RULES_VERSION,
    FRAUD_RULES_VERSION,
)


# ---------------------------------------------------------------------------
# 1. Cálculo de cuota fija
# ---------------------------------------------------------------------------

class TestFixedPayment:
    def test_basic_pmt(self):
        """
        PMT conocido: P=12 000 000, TEA=18%, n=36.
        TM = (1.18)^(1/12) - 1 ≈ 0.013888
        PMT ≈ 433 400 (verificado con hoja de cálculo).
        """
        tm = _monthly_rate(0.18)
        pmt = _fixed_payment(12_000_000, tm, 36)
        assert 420_000 < pmt < 450_000, f"PMT inesperado: {pmt}"

    def test_zero_rate(self):
        """Con tasa 0, la cuota es P/n."""
        pmt = _fixed_payment(6_000_000, 0.0, 12)
        assert math.isclose(pmt, 500_000.0, rel_tol=1e-9)

    def test_monthly_rate_conversion(self):
        """TEA 0% → TM 0%; TEA 100% → TM ≈ 5.946%."""
        assert math.isclose(_monthly_rate(0.0), 0.0, abs_tol=1e-12)
        tm_100 = _monthly_rate(1.0)
        assert math.isclose(tm_100, 2 ** (1 / 12) - 1, rel_tol=1e-9)

    def test_total_payment(self):
        """El total a pagar debe ser mayor que el principal."""
        tm = _monthly_rate(0.18)
        pmt = _fixed_payment(10_000_000, tm, 24)
        total = pmt * 24
        assert total > 10_000_000


# ---------------------------------------------------------------------------
# 2. Score determinista
# ---------------------------------------------------------------------------

class TestCreditScore:
    def test_score_range(self):
        """El score de cualquier cliente con datos completos debe estar en [300, 850]."""
        for cid in [f"DEMO-{i:03d}" for i in range(1, 12)]:
            result = calculate_credit_score(cid)
            if result["status"] == "ok":
                assert 300 <= result["score"] <= 850, (
                    f"{cid}: score {result['score']} fuera de rango"
                )

    def test_demo_003_high_score(self):
        """DEMO-003: ingresos altos, mora 0, utilización baja → score alto (>= 700)."""
        r = calculate_credit_score("DEMO-003")
        assert r["status"] == "ok"
        assert r["score"] >= 700, f"Esperado >= 700, obtenido {r['score']}"

    def test_demo_010_low_score(self):
        """DEMO-010: mora 60 días, utilización 95%, DTI alto → score bajo (< 500)."""
        r = calculate_credit_score("DEMO-010")
        assert r["status"] == "ok"
        assert r["score"] < 500, f"Esperado < 500, obtenido {r['score']}"

    def test_rules_version(self):
        r = calculate_credit_score("DEMO-001")
        assert r["rules_version"] == SCORE_RULES_VERSION

    def test_not_found(self):
        r = calculate_credit_score("DEMO-999")
        assert r["status"] == "not_found"
        assert r["score"] is None

    def test_breakdown_keys(self):
        r = calculate_credit_score("DEMO-007")
        assert r["status"] == "ok"
        bd = r["breakdown"]
        for key in ("dti_ratio", "partial_dti", "partial_utilization",
                    "partial_overdue", "partial_history", "composite", "weights"):
            assert key in bd, f"Falta clave '{key}' en breakdown"

    def test_deterministic(self):
        """Mismo cliente → mismo score en llamadas sucesivas."""
        r1 = calculate_credit_score("DEMO-005")
        r2 = calculate_credit_score("DEMO-005")
        assert r1["score"] == r2["score"]


# ---------------------------------------------------------------------------
# 3. Información insuficiente — DEMO-012
# ---------------------------------------------------------------------------

class TestInsufficientData:
    def test_score_insufficient(self):
        """DEMO-012 tiene ingresos == 0 → insufficient_data."""
        r = calculate_credit_score("DEMO-012")
        assert r["status"] == "insufficient_data"
        assert r["score"] is None

    def test_loan_insufficient(self):
        """Evaluar crédito para DEMO-012 → decision insufficient_data."""
        r = evaluate_loan("DEMO-012", 5_000_000, 24, 0.18)
        assert r["decision"] == "insufficient_data"
        assert r["decision_code"] == "INSUF_DATA"
        assert r["loan_simulation"] is None


# ---------------------------------------------------------------------------
# 4. Alerta HIGH — DEMO-001
# ---------------------------------------------------------------------------

class TestFraudAlerts:
    def test_high_alert_demo_001(self):
        """
        DEMO-001 con monto > 5× ingresos (4 500 000 × 5 = 22 500 000) y 3 solicitudes
        previas en < 60 min → R1 + R3 activas → alert_level HIGH.
        """
        # Monto = 25 000 000 > 22 500 000 (5× ingresos DEMO-001) → R3
        # DEMO-001 tiene 3 solicitudes en el historial (REQ-001/002/003) en < 60 min → R1
        r = check_fraud_signals("DEMO-001", 25_000_000, "DEV-AAA")
        assert r["alert_level"] == "HIGH", (
            f"Esperado HIGH, obtenido {r['alert_level']}. Señales: {r['signals']}"
        )
        assert r["signals_count"] >= 2

    def test_low_alert_clean_customer(self):
        """DEMO-007 sin historial de riesgo, monto razonable → alerta LOW."""
        r = check_fraud_signals("DEMO-007", 5_000_000, "DEV-NUEVO-XYZ")
        assert r["alert_level"] == "LOW"

    def test_unusual_amount_rule(self):
        """DEMO-006: monto > 5× ingresos (1 900 000) → R3 activa."""
        # umbral = 1_900_000 * 5 = 9_500_000
        r = check_fraud_signals("DEMO-006", 10_000_000, "DEV-NUEVO-ZZZ")
        rule_ids = [s["rule_id"] for s in r["signals"]]
        assert "R3" in rule_ids, f"R3 no detectada. Señales: {r['signals']}"

    def test_device_multi_client_rule(self):
        """DEV-BBB está asociado a DEMO-002 y DEMO-003 → R2 activa para DEMO-005."""
        r = check_fraud_signals("DEMO-005", 1_000_000, "DEV-BBB")
        rule_ids = [s["rule_id"] for s in r["signals"]]
        assert "R2" in rule_ids, f"R2 no detectada. Señales: {r['signals']}"

    def test_fraud_disclaimer_present(self):
        r = check_fraud_signals("DEMO-001", 1_000_000, "DEV-AAA")
        assert "disclaimer" in r


# ---------------------------------------------------------------------------
# 5. Evaluación de crédito — casos extremos
# ---------------------------------------------------------------------------

class TestLoanEvaluation:
    def test_approved_demo_003(self):
        r = evaluate_loan("DEMO-003", 20_000_000, 36, 0.18)
        assert r["decision"] == "approved"

    def test_rejected_demo_010(self):
        r = evaluate_loan("DEMO-010", 5_000_000, 24, 0.18)
        assert r["decision"] == "rejected"

    def test_rules_version_present(self):
        r = evaluate_loan("DEMO-001", 10_000_000, 24, 0.18)
        assert r["rules_version"] == LOAN_RULES_VERSION

    def test_simulation_values_positive(self):
        r = evaluate_loan("DEMO-007", 30_000_000, 60, 0.15)
        sim = r["loan_simulation"]
        assert sim["fixed_payment_cop"] > 0
        assert sim["total_payment_cop"] > sim["amount_cop"]
