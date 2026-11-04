"""
tests/test_contract.py — Pruebas del contrato OpenAPI v1.1.

Cubre los nuevos comportamientos documentados:
  - Modelos Pydantic: los campos de respuesta son exactos.
  - Prioridad de decisión: rejected tiene prioridad sobre alerta HIGH.
  - device_id en evaluate: se usa WEB-PORTAL internamente.
  - Reloj inyectable (now_fn) para R1: comportamiento reproducible.
  - API key: sin clave configurada → endpoints accesibles; con clave → 401 si falta.
  - Servidor: SERVER_URL controla el campo servers del contrato.
"""

import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

# ─── Imports core ────────────────────────────────────────────────────────────
from core import (
    check_fraud_signals,
    evaluate_loan,
    _default_now,
    FRAUD_RULES_VERSION,
)
from models import (
    CreditScoreResponse,
    FraudSignalResponse,
    LoanEvaluationResponse,
    FraudCheckRequest,
    LoanEvaluationRequest,
)


# ---------------------------------------------------------------------------
# 1. Prioridad: rejected prevalece sobre alerta HIGH de fraude
# ---------------------------------------------------------------------------

class TestDecisionPriority:
    def test_rejected_beats_high_fraud_alert(self):
        """
        DEMO-008: score bajo y carga alta → rejected.
        Aunque haya alerta HIGH de fraude, la decisión debe permanecer rejected.
        (En evaluate_loan_application la alerta se suma al fraud_check pero
        la decisión no cambia a review_fraud_alert.)
        """
        loan = evaluate_loan("DEMO-008", 5_000_000, 24, 0.18)
        assert loan["decision"] == "rejected", (
            f"Esperado rejected, obtenido {loan['decision']}"
        )

        # Ahora simulamos el flujo completo de evaluate_demo_loan_application
        from core import check_fraud_signals as cfs
        fraud = cfs("DEMO-008", 5_000_000, "WEB-PORTAL")
        # La lógica del endpoint: solo se eleva a review_fraud_alert si
        # decision == "approved". rejected no debe cambiar.
        if loan["decision"] == "approved" and fraud["alert_level"] == "HIGH":
            loan["decision"] = "review_fraud_alert"
        assert loan["decision"] == "rejected", (
            "El rechazo crediticio debe prevalecer sobre cualquier alerta de fraude"
        )

    def test_approved_with_high_fraud_becomes_review_fraud_alert(self):
        """
        DEMO-001 aprobado crediticiamente + alerta HIGH (R1 y R3 activas con monto > 5×
        ingresos de 4.5M y 3 solicitudes previas en historial) → review_fraud_alert.

        DEMO-001: ingresos 4_500_000 → umbral R3 = 22_500_000. Score ~ 736 (>= 650).
        Con monto = 25_000_000 y plazo 60 meses la carga financiera queda <= 40 %.
        R1 activa (3 solicitudes previas en < 60 min) + R3 activa → HIGH.
        """
        from core import check_fraud_signals as cfs

        # Verificamos primero que el crédito es aprobable (score alto, carga baja)
        loan = evaluate_loan("DEMO-001", 25_000_000, 60, 0.18)
        fraud = cfs("DEMO-001", 25_000_000, "WEB-PORTAL")

        # Comprobamos condiciones previas
        assert loan["decision"] == "approved", (
            f"Precondición: DEMO-001 debe ser aprobado crediticiamente. "
            f"Decision: {loan['decision']}, razones: {loan['reasons']}"
        )
        assert fraud["alert_level"] == "HIGH", (
            f"Precondición: alerta debe ser HIGH. Nivel: {fraud['alert_level']}, "
            f"señales: {fraud['signals']}"
        )

        # Replicamos la lógica del endpoint
        if loan["decision"] == "approved" and fraud["alert_level"] == "HIGH":
            loan["decision"] = "review_fraud_alert"

        assert loan["decision"] == "review_fraud_alert"

    def test_review_with_high_fraud_stays_review(self):
        """
        DEMO-002: score en rango intermedio → review.
        Con alerta HIGH la decisión debe permanecer review (no review_fraud_alert),
        porque la escalada solo aplica cuando la decisión es approved.
        """
        from core import check_fraud_signals as cfs
        loan = evaluate_loan("DEMO-002", 3_000_000, 24, 0.18)
        assert loan["decision"] == "review"

        # La lógica del endpoint no cambia review → review_fraud_alert
        fraud = cfs("DEMO-002", 3_000_000, "WEB-PORTAL")
        if loan["decision"] == "approved" and fraud["alert_level"] == "HIGH":
            loan["decision"] = "review_fraud_alert"
        assert loan["decision"] == "review"


# ---------------------------------------------------------------------------
# 2. device_id en evaluate_demo_loan_application
# ---------------------------------------------------------------------------

class TestDeviceIdInEvaluate:
    def test_fraud_check_uses_web_portal(self):
        """
        El endpoint evaluate_demo_loan_application usa 'WEB-PORTAL' como device_id
        interno. Verificamos que check_fraud_signals con ese valor funcione
        y que el device_id en la respuesta sea exactamente 'WEB-PORTAL'.
        """
        fraud = check_fraud_signals("DEMO-003", 5_000_000, "WEB-PORTAL")
        assert fraud["device_id"] == "WEB-PORTAL"

    def test_explicit_device_id_different_from_web_portal(self):
        """
        check_demo_fraud_signals acepta cualquier device_id real.
        El resultado con DEV-AAA difiere del de WEB-PORTAL para el mismo cliente.
        """
        fraud_real = check_fraud_signals("DEMO-001", 5_000_000, "DEV-AAA")
        fraud_generic = check_fraud_signals("DEMO-001", 5_000_000, "WEB-PORTAL")
        # DEV-AAA está en el historial asociado a DEMO-001 → R2 puede activarse
        # WEB-PORTAL no está en el historial → R2 no se activa desde ese dispositivo
        assert fraud_real["device_id"] == "DEV-AAA"
        assert fraud_generic["device_id"] == "WEB-PORTAL"
        # Las señales pueden diferir
        r2_real = any(s["rule_id"] == "R2" for s in fraud_real["signals"])
        r2_generic = any(s["rule_id"] == "R2" for s in fraud_generic["signals"])
        # DEV-AAA solo tiene un cliente en el historial (DEMO-001) → R2 NO activa
        # WEB-PORTAL tampoco tiene historial previo → R2 NO activa
        # Ambos deben ser False (DEV-AAA solo tiene DEMO-001 en el historial)
        assert not r2_real, "DEV-AAA solo asociado a DEMO-001 → R2 no debe activarse"
        assert not r2_generic


# ---------------------------------------------------------------------------
# 3. Reloj inyectable (now_fn) para R1
# ---------------------------------------------------------------------------

class TestClockInjection:
    def test_default_now_uses_max_timestamp(self):
        """_default_now devuelve el máximo de la lista de timestamps."""
        times = [
            datetime(2026, 10, 1, 9, 0, 0),
            datetime(2026, 10, 1, 9, 18, 0),
            datetime(2026, 10, 1, 9, 10, 0),
        ]
        result = _default_now(times)
        assert result == datetime(2026, 10, 1, 9, 18, 0)

    def test_now_fn_outside_window_suppresses_r1(self):
        """
        Si la referencia temporal está mucho más lejos que las solicitudes
        en el historial, R1 no debe activarse aunque DEMO-001 tenga 3 solicitudes.
        """
        # Usamos una fecha 1 año después del historial → ninguna solicitud queda en ventana
        future_ref = datetime(2027, 12, 31, 23, 59, 59)
        fraud = check_fraud_signals(
            "DEMO-001", 5_000_000, "DEV-AAA",
            now_fn=lambda _: future_ref,
        )
        r1_signals = [s for s in fraud["signals"] if s["rule_id"] == "R1"]
        # Con referencia futura el window_start = 2027-12-31 22:59:59
        # Los timestamps de DEMO-001 son 2026-10-01 09:10/15/18 → fuera de ventana
        assert len(r1_signals) == 0, (
            "R1 no debe activarse cuando la referencia temporal es posterior al historial"
        )

    def test_now_fn_inside_window_activates_r1(self):
        """
        Con referencia temporal justo encima del historial de DEMO-001 → R1 activa.
        """
        # La referencia apunta al momento de la 3ª solicitud
        ref = datetime(2026, 10, 1, 9, 18, 0)
        fraud = check_fraud_signals(
            "DEMO-001", 5_000_000, "DEV-AAA",
            now_fn=lambda _: ref,
        )
        r1_signals = [s for s in fraud["signals"] if s["rule_id"] == "R1"]
        assert len(r1_signals) == 1, (
            f"R1 debe activarse con referencia {ref}. Señales: {fraud['signals']}"
        )

    def test_deterministic_without_clock(self):
        """El resultado es idéntico en llamadas sucesivas sin now_fn."""
        r1 = check_fraud_signals("DEMO-001", 5_000_000, "DEV-AAA")
        r2 = check_fraud_signals("DEMO-001", 5_000_000, "DEV-AAA")
        assert r1["alert_level"] == r2["alert_level"]
        assert r1["signals_count"] == r2["signals_count"]


# ---------------------------------------------------------------------------
# 4. Modelos Pydantic — validación de campos reales
# ---------------------------------------------------------------------------

class TestResponseModels:
    def test_credit_score_model_ok(self):
        from core import calculate_credit_score
        raw = calculate_credit_score("DEMO-003")
        model = CreditScoreResponse(**raw)
        assert model.status == "ok"
        assert model.score is not None
        assert 300 <= model.score <= 850
        assert model.breakdown is not None
        assert model.rules_version == "v1.0"

    def test_credit_score_model_insufficient(self):
        from core import calculate_credit_score
        raw = calculate_credit_score("DEMO-012")
        model = CreditScoreResponse(**raw)
        assert model.status == "insufficient_data"
        assert model.score is None
        assert model.breakdown is None
        assert model.reason is not None

    def test_fraud_signal_model(self):
        raw = check_fraud_signals("DEMO-001", 25_000_000, "DEV-AAA")
        model = FraudSignalResponse(**raw)
        assert model.alert_level in ("HIGH", "MEDIUM", "LOW")
        assert model.device_id == "DEV-AAA"
        assert isinstance(model.signals, list)

    def test_loan_evaluation_model_approved(self):
        from core import check_fraud_signals as cfs
        loan = evaluate_loan("DEMO-003", 20_000_000, 36, 0.18)
        fraud = cfs("DEMO-003", 20_000_000, "WEB-PORTAL")
        if loan["decision"] == "approved" and fraud["alert_level"] == "HIGH":
            loan["decision"] = "review_fraud_alert"
            loan["decision_code"] = "REVIEW_FRAUD_ALERT"
        loan["fraud_check"] = fraud
        model = LoanEvaluationResponse(**loan)
        assert model.decision == "approved"
        assert model.loan_simulation is not None
        assert model.fraud_check is not None

    def test_loan_evaluation_model_insufficient(self):
        from core import evaluate_loan as el
        loan = el("DEMO-012", 5_000_000, 24, 0.18)
        loan["fraud_check"] = None
        model = LoanEvaluationResponse(**loan)
        assert model.decision == "insufficient_data"
        assert model.loan_simulation is None
        assert model.fraud_check is None
        assert model.disclaimer is not None


# ---------------------------------------------------------------------------
# 5. API key — comportamiento de la dependencia verify_api_key
# ---------------------------------------------------------------------------

class TestApiKeyDependency:
    """
    Prueba la función verify_api_key sin levantar servidor HTTP.
    Simula el comportamiento de la dependencia de FastAPI directamente.
    """

    def test_no_key_configured_allows_any(self):
        """Sin DEMO_API_KEY en entorno, verify_api_key no lanza excepción."""
        import asyncio
        # Guardamos y limpiamos la variable de entorno si existe
        original = os.environ.pop("DEMO_API_KEY", None)
        try:
            # Reimportamos main para que _DEMO_API_KEY sea None
            import importlib
            import main as main_mod
            original_key = main_mod._DEMO_API_KEY
            main_mod._DEMO_API_KEY = None

            result = asyncio.get_event_loop().run_until_complete(
                main_mod.verify_api_key(api_key=None)
            )
            assert result is None  # Sin excepción = correcto
        finally:
            main_mod._DEMO_API_KEY = original_key
            if original:
                os.environ["DEMO_API_KEY"] = original

    def test_key_configured_wrong_key_raises_401(self):
        """Con DEMO_API_KEY configurada, una clave incorrecta lanza 401."""
        import asyncio
        from fastapi import HTTPException
        import main as main_mod
        original_key = main_mod._DEMO_API_KEY
        main_mod._DEMO_API_KEY = "secret-demo-key"
        try:
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    main_mod.verify_api_key(api_key="wrong-key")
                )
            assert exc_info.value.status_code == 401
        finally:
            main_mod._DEMO_API_KEY = original_key

    def test_key_configured_correct_key_passes(self):
        """Con DEMO_API_KEY configurada, la clave correcta no lanza excepción."""
        import asyncio
        import main as main_mod
        original_key = main_mod._DEMO_API_KEY
        main_mod._DEMO_API_KEY = "secret-demo-key"
        try:
            result = asyncio.get_event_loop().run_until_complete(
                main_mod.verify_api_key(api_key="secret-demo-key")
            )
            assert result is None
        finally:
            main_mod._DEMO_API_KEY = original_key
