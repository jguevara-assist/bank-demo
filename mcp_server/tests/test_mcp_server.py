"""
tests/test_mcp_server.py — Pruebas del servidor MCP de Banco Demo.

Estrategia:
  - Mockea httpx para no requerir el backend bancario en ejecución.
  - Prueba directamente las funciones de herramienta registradas en el servidor.
  - Prueba el middleware de autenticación bearer.
  - Prueba que la URL de destino nunca puede ser modificada por argumentos.
  - Prueba que errores HTTP del backend se propagan como errores estructurados.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── imports del servidor ────────────────────────────────────────────────────
import server as srv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_bank_url(monkeypatch):
    """Asegura que BANK_API_BASE_URL sea el valor configurado en el módulo."""
    monkeypatch.setattr(
        srv, "BANK_API_BASE_URL",
        "https://banco-demo-demo-bank.apps.itz-m23snt.infra01-lb.wdc04.techzone.ibm.com",
    )


def _mock_response(data: dict, status_code: int = 200):
    """Crea un mock de httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = status_code < 400
    resp.json.return_value = data
    resp.text = json.dumps(data)
    return resp


# ---------------------------------------------------------------------------
# 1. list_demo_customers — respuesta correcta del backend
# ---------------------------------------------------------------------------

class TestListDemoCustomers:
    @pytest.mark.asyncio
    async def test_returns_customers(self):
        payload = {"total": 12, "customers": [{"id": "DEMO-001"}], "disclaimer": "demo"}
        mock_resp = _mock_response(payload)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await srv.list_demo_customers()

        assert result["total"] == 12
        assert result["customers"][0]["id"] == "DEMO-001"

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        import httpx as _httpx
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
            mock_client_cls.return_value = mock_client

            result = await srv.list_demo_customers()

        assert "error" in result
        assert "Tiempo de espera" in result["error"]


# ---------------------------------------------------------------------------
# 2. get_customer_credit_profile — 404 se propaga como error
# ---------------------------------------------------------------------------

class TestGetCustomerProfile:
    @pytest.mark.asyncio
    async def test_not_found_returns_error(self):
        mock_resp = _mock_response({"detail": "not found"}, status_code=404)
        mock_resp.is_success = False
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await srv.get_customer_credit_profile("DEMO-999")

        assert "error" in result
        assert "404" in result["error"] or "no encontrado" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_valid_customer_returns_profile(self):
        payload = {
            "customer": {"id": "DEMO-001", "monthly_income": 4500000},
            "request_history": [],
            "disclaimer": "demo",
        }
        mock_resp = _mock_response(payload)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await srv.get_customer_credit_profile("DEMO-001")

        assert result["customer"]["id"] == "DEMO-001"


# ---------------------------------------------------------------------------
# 3. calculate_demo_credit_score — insufficient_data preservado
# ---------------------------------------------------------------------------

class TestCreditScore:
    @pytest.mark.asyncio
    async def test_insufficient_data_preserved(self):
        payload = {
            "customer_id": "DEMO-012",
            "status": "insufficient_data",
            "score": None,
            "rules_version": "v1.0",
            "reason": "Ingresos iguales a cero o no informados.",
        }
        mock_resp = _mock_response(payload)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await srv.calculate_demo_credit_score("DEMO-012")

        assert result["status"] == "insufficient_data"
        assert result["score"] is None
        assert "Ingresos" in result["reason"]


# ---------------------------------------------------------------------------
# 4. check_demo_fraud_signals — señales preservadas, POST no se reintenta
# ---------------------------------------------------------------------------

class TestFraudSignals:
    @pytest.mark.asyncio
    async def test_high_alert_preserved(self):
        payload = {
            "customer_id": "DEMO-001",
            "device_id": "DEV-AAA",
            "alert_level": "HIGH",
            "signals_count": 2,
            "signals": [
                {"rule_id": "R1", "rule_name": "MULTIPLE_REQUESTS", "detail": "..."},
                {"rule_id": "R3", "rule_name": "UNUSUAL_AMOUNT", "detail": "..."},
            ],
            "recommendation": "Revisión automática.",
            "rules_version": "v1.0",
            "disclaimer": "Alertas indicativas.",
        }
        mock_resp = _mock_response(payload)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await srv.check_demo_fraud_signals(
                customer_id="DEMO-001", amount=25_000_000, device_id="DEV-AAA"
            )

        assert result["alert_level"] == "HIGH"
        assert result["signals_count"] == 2
        rule_ids = [s["rule_id"] for s in result["signals"]]
        assert "R1" in rule_ids and "R3" in rule_ids

        # Verificar que POST fue llamado exactamente una vez (sin reintentos)
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_422_returns_error(self):
        mock_resp = _mock_response({"detail": [{"loc": ["amount"], "msg": "gt 0"}]}, status_code=422)
        mock_resp.is_success = False
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await srv.check_demo_fraud_signals(
                customer_id="DEMO-001", amount=-1, device_id="DEV-X"
            )

        assert "error" in result
        assert "422" in result["error"]


# ---------------------------------------------------------------------------
# 5. evaluate_demo_loan_application — todos los campos de respuesta preservados
# ---------------------------------------------------------------------------

class TestLoanEvaluation:
    @pytest.mark.asyncio
    async def test_approved_response_preserved(self):
        payload = {
            "customer_id": "DEMO-003",
            "decision": "approved",
            "decision_code": "APPROVED",
            "reasons": ["Score 791 >= 650 y carga financiera 18.83% <= 40%."],
            "loan_simulation": {
                "amount_cop": 20_000_000,
                "term_months": 36,
                "annual_effective_rate": 0.18,
                "monthly_rate": 0.01388,
                "fixed_payment_cop": 723680.0,
                "total_payment_cop": 26_052_480.0,
                "new_debt_to_income": 0.2099,
            },
            "score_summary": {"score": 791, "status": "ok", "rules_version": "v1.0"},
            "fraud_check": {
                "alert_level": "LOW",
                "signals_count": 0,
                "signals": [],
                "device_id": "WEB-PORTAL",
            },
            "rules_version": "v1.0",
            "disclaimer": "Demo.",
        }
        mock_resp = _mock_response(payload)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await srv.evaluate_demo_loan_application(
                customer_id="DEMO-003",
                amount=20_000_000,
                term_months=36,
                annual_effective_rate=0.18,
            )

        assert result["decision"] == "approved"
        assert result["decision_code"] == "APPROVED"
        assert result["loan_simulation"]["fixed_payment_cop"] == 723680.0
        assert result["fraud_check"]["device_id"] == "WEB-PORTAL"

    @pytest.mark.asyncio
    async def test_no_retry_on_post_error(self):
        """Las operaciones POST no deben reintentarse automáticamente."""
        import httpx as _httpx
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(
                side_effect=_httpx.RequestError("connection failed")
            )
            mock_client_cls.return_value = mock_client

            result = await srv.evaluate_demo_loan_application(
                customer_id="DEMO-003", amount=10_000_000,
                term_months=24, annual_effective_rate=0.18,
            )

        assert "error" in result
        # Exactamente una llamada — sin reintentos
        assert mock_client.post.call_count == 1


# ---------------------------------------------------------------------------
# 6. URL de destino fija — argumentos no pueden cambiar el host
# ---------------------------------------------------------------------------

class TestFixedBankUrl:
    @pytest.mark.asyncio
    async def test_valid_customer_id_calls_backend(self):
        """Un customer_id válido llama al backend con la URL base correcta."""
        captured_urls = []
        mock_resp = _mock_response({"customer": {"id": "DEMO-001"}, "request_history": [], "disclaimer": ""})

        async def capturing_get(url, **kwargs):
            captured_urls.append(url)
            return mock_resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = capturing_get
            mock_client_cls.return_value = mock_client

            await srv.get_customer_credit_profile("DEMO-001")

        assert len(captured_urls) == 1
        assert captured_urls[0].startswith(srv.BANK_API_BASE_URL)
        assert "DEMO-001" in captured_urls[0]

    @pytest.mark.asyncio
    async def test_path_traversal_rejected_before_http(self):
        """
        customer_id con path traversal es rechazado por _safe_customer_id
        antes de llegar a httpx. El backend nunca recibe la petición.
        """
        captured_urls = []

        async def capturing_get(url, **kwargs):
            captured_urls.append(url)
            return _mock_response({})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = capturing_get
            mock_client_cls.return_value = mock_client

            result = await srv.get_customer_credit_profile("../../etc/passwd")

        # El backend nunca fue llamado
        assert len(captured_urls) == 0, "El backend no debe recibir peticiones con customer_id inválido"
        # La herramienta devuelve un error estructurado
        assert "error" in result
        assert "inválido" in result["error"] or "customer_id" in result["error"]


# ---------------------------------------------------------------------------
# 7. Middleware de autenticación bearer
# ---------------------------------------------------------------------------

class TestBearerAuthMiddleware:
    @pytest.mark.asyncio
    async def test_health_always_allowed(self):
        """El endpoint /health no requiere autenticación."""
        from fastapi.testclient import TestClient

        original = srv.MCP_BEARER_TOKEN
        try:
            srv.MCP_BEARER_TOKEN = "secret-test-token"
            # El TestClient sincrono no puede testear Streamable HTTP fácilmente,
            # verificamos la lógica del middleware directamente.
            request_mock = MagicMock()
            request_mock.url.path = "/health"
            request_mock.headers = {}

            next_called = False
            async def call_next(req):
                nonlocal next_called
                next_called = True
                from fastapi.responses import JSONResponse
                return JSONResponse({"status": "ok"})

            await srv.bearer_auth_middleware(request_mock, call_next)
            assert next_called, "/health debe pasar sin autenticación"
        finally:
            srv.MCP_BEARER_TOKEN = original

    @pytest.mark.asyncio
    async def test_mcp_without_token_returns_401(self):
        """Acceso a /mcp sin Bearer token devuelve 401."""
        original = srv.MCP_BEARER_TOKEN
        try:
            srv.MCP_BEARER_TOKEN = "secret-test-token"

            request_mock = MagicMock()
            request_mock.url.path = "/mcp"
            request_mock.headers = MagicMock()
            request_mock.headers.get = MagicMock(return_value="")

            async def call_next(req):
                pytest.fail("call_next no debe invocarse sin autenticación")

            response = await srv.bearer_auth_middleware(request_mock, call_next)
            assert response.status_code == 401
        finally:
            srv.MCP_BEARER_TOKEN = original

    @pytest.mark.asyncio
    async def test_mcp_with_correct_token_passes(self):
        """Bearer token correcto permite acceso a /mcp."""
        original = srv.MCP_BEARER_TOKEN
        try:
            srv.MCP_BEARER_TOKEN = "secret-test-token"

            request_mock = MagicMock()
            request_mock.url.path = "/mcp"
            request_mock.headers = MagicMock()
            request_mock.headers.get = MagicMock(return_value="Bearer secret-test-token")

            next_called = False
            async def call_next(req):
                nonlocal next_called
                next_called = True
                from fastapi.responses import JSONResponse
                return JSONResponse({"ok": True})

            await srv.bearer_auth_middleware(request_mock, call_next)
            assert next_called, "call_next debe invocarse con token correcto"
        finally:
            srv.MCP_BEARER_TOKEN = original

    @pytest.mark.asyncio
    async def test_no_bearer_configured_all_pass(self):
        """Sin MCP_BEARER_TOKEN configurado, todos los paths pasan."""
        original = srv.MCP_BEARER_TOKEN
        try:
            srv.MCP_BEARER_TOKEN = None

            request_mock = MagicMock()
            request_mock.url.path = "/mcp"
            request_mock.headers = MagicMock()
            request_mock.headers.get = MagicMock(return_value="")

            next_called = False
            async def call_next(req):
                nonlocal next_called
                next_called = True
                from fastapi.responses import JSONResponse
                return JSONResponse({"ok": True})

            await srv.bearer_auth_middleware(request_mock, call_next)
            assert next_called, "Sin bearer configurado, todo debe pasar"
        finally:
            srv.MCP_BEARER_TOKEN = original


# ---------------------------------------------------------------------------
# 8. _call_bank — headers correctos (sin secretos registrados)
# ---------------------------------------------------------------------------

class TestCallBankHeaders:
    @pytest.mark.asyncio
    async def test_correlation_id_propagated(self):
        """X-Correlation-ID se propaga al backend."""
        captured_headers = {}
        mock_resp = _mock_response({"ok": True})

        async def capturing_get(url, headers=None, **kwargs):
            captured_headers.update(headers or {})
            return mock_resp

        original_key = srv.BANK_API_KEY
        srv.BANK_API_KEY = None
        try:
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = capturing_get
                mock_client_cls.return_value = mock_client

                await srv._call_bank("GET", "/api/customers", "test-correlation-123")
        finally:
            srv.BANK_API_KEY = original_key

        assert "X-Correlation-ID" in captured_headers
        assert captured_headers["X-Correlation-ID"] == "test-correlation-123"
        assert "X-API-Key" not in captured_headers  # No bank key configurada

    @pytest.mark.asyncio
    async def test_bank_api_key_sent_when_configured(self):
        """X-API-Key se envía cuando BANK_API_KEY está configurada."""
        captured_headers = {}
        mock_resp = _mock_response({"ok": True})

        async def capturing_get(url, headers=None, **kwargs):
            captured_headers.update(headers or {})
            return mock_resp

        original_key = srv.BANK_API_KEY
        srv.BANK_API_KEY = "my-test-bank-key"
        try:
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = capturing_get
                mock_client_cls.return_value = mock_client

                await srv._call_bank("GET", "/api/customers", "corr-456")
        finally:
            srv.BANK_API_KEY = original_key

        assert captured_headers.get("X-API-Key") == "my-test-bank-key"
