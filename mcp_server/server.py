"""
server.py — Servidor MCP para Banco Demo — Créditos y Fraude.

SDK: mcp >= 2.0 (MCPServer, run_streamable_http_async)
Transporte: Streamable HTTP en /mcp
Auth interna: Bearer token configurable (MCP_BEARER_TOKEN)

ARQUITECTURA DE SEGURIDAD
─────────────────────────
Se separan tres capas de credenciales:

1. Autenticación del cliente MCP ante API Connect (IBM APIC):
   El cliente se autentica ante IBM API Connect con sus propias credenciales
   (API key, OAuth, etc.). API Connect es el único punto de entrada público.

2. Protección del servidor MCP frente a accesos directos (que eludan APIC):
   El servidor exige `Authorization: Bearer <MCP_BEARER_TOKEN>` en cada
   petición a /mcp. Este token lo conoce solo API Connect, que lo inyecta
   como header estático en la política de backend (invoke policy). El token
   del cliente/usuario nunca llega al servidor MCP.

   Configuración en APIC (invoke policy, header estático):
     Header name:  Authorization
     Header value: Bearer $(catalog.properties.MCP_BEARER_TOKEN)
   El valor se guarda en las propiedades del catálogo de APIC, no en el
   contrato ni en el código.

3. Credenciales del servidor MCP ante el backend bancario:
   Si el backend FastAPI tiene DEMO_API_KEY activada, el servidor MCP la
   incluye como `X-API-Key` en cada llamada. Se configura en BANK_API_KEY.

VARIABLES DE ENTORNO
────────────────────
  MCP_BEARER_TOKEN   Bearer token para proteger /mcp.
                     Vacío = sin protección (solo local/dev).
  BANK_API_BASE_URL  URL base del backend bancario.
  BANK_API_KEY       API key del backend (X-API-Key). Vacío = sin header.
  MCP_HOST           Host. Default: 0.0.0.0
  MCP_PORT           Puerto. Default: 8080
  MCP_ALLOWED_HOSTS  Hosts admitidos por el transporte MCP, separados por comas.
                     Default: localhost y DNS internos del Service en demo-bank.
  REQUEST_TIMEOUT    Timeout en segundos. Default: 15
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

log = logging.getLogger("banco-demo-mcp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

BANK_API_BASE_URL: str = os.environ.get(
    "BANK_API_BASE_URL",
    "https://banco-demo-demo-bank.apps.itz-m23snt.infra01-lb.wdc04.techzone.ibm.com",
).rstrip("/")

BANK_API_KEY: str | None = os.environ.get("BANK_API_KEY") or None
MCP_BEARER_TOKEN: str | None = os.environ.get("MCP_BEARER_TOKEN") or None
REQUEST_TIMEOUT: float = float(os.environ.get("REQUEST_TIMEOUT", "15"))
MCP_HOST: str = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(os.environ.get("MCP_PORT", "8080"))
MCP_ALLOWED_HOSTS: list[str] = [
    host.strip()
    for host in os.environ.get(
        "MCP_ALLOWED_HOSTS",
        "localhost,localhost:*,127.0.0.1,127.0.0.1:*,"
        "banco-demo-mcp,banco-demo-mcp:*,"
        "banco-demo-mcp.demo-bank,banco-demo-mcp.demo-bank:*,"
        "banco-demo-mcp.demo-bank.svc,banco-demo-mcp.demo-bank.svc:*,"
        "banco-demo-mcp.demo-bank.svc.cluster.local,"
        "banco-demo-mcp.demo-bank.svc.cluster.local:*",
    ).split(",")
    if host.strip()
]

if MCP_BEARER_TOKEN:
    log.info("MCP_BEARER_TOKEN configurado — /mcp protegido.")
else:
    log.warning("MCP_BEARER_TOKEN no configurado — /mcp es público (solo dev).")

if BANK_API_KEY:
    log.info("BANK_API_KEY configurado — X-API-Key se enviará al backend.")


# ---------------------------------------------------------------------------
# Cliente HTTP al backend bancario
# ---------------------------------------------------------------------------

def _build_bank_headers(correlation_id: str) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json",
        "X-Correlation-ID": correlation_id,
    }
    if BANK_API_KEY:
        headers["X-API-Key"] = BANK_API_KEY
    return headers


def _safe_customer_id(customer_id: str) -> str:
    """
    Valida que customer_id sea seguro para incluir en un path HTTP.
    Acepta solo caracteres alfanuméricos y guiones, como DEMO-001.
    Rechaza path traversal, inyección de URLs, etc.
    """
    import re
    if not re.fullmatch(r"[A-Za-z0-9\-]{1,50}", customer_id):
        raise RuntimeError(
            f"customer_id inválido: {customer_id!r}. "
            "Solo se aceptan caracteres alfanuméricos y guiones (ej. DEMO-001)."
        )
    return customer_id


async def _call_bank(
    method: str,
    path: str,
    correlation_id: str,
    *,
    json_body: dict | None = None,
) -> dict[str, Any]:
    """
    Llama al backend bancario con URL base fija.

    - Los argumentos de herramienta nunca pueden cambiar el host de destino.
    - El path se construye internamente; customer_id es validado por _safe_customer_id.
    - POST no se reintenta automáticamente.
    - X-Correlation-ID se propaga siempre.
    - Secretos nunca se registran en logs.
    """
    url = f"{BANK_API_BASE_URL}{path}"
    headers = _build_bank_headers(correlation_id)
    log.info("bank_call method=%s path=%s corr=%s", method, path, correlation_id)

    try:
        async with httpx.AsyncClient(verify=True, timeout=REQUEST_TIMEOUT) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=json_body)
            else:
                raise ValueError(f"Método HTTP no soportado: {method}")
    except httpx.TimeoutException:
        raise RuntimeError(
            f"Tiempo de espera agotado contactando el backend "
            f"(timeout={REQUEST_TIMEOUT}s, path={path})."
        )
    except httpx.RequestError as e:
        raise RuntimeError(f"Error de red al contactar el backend: {e}")

    if resp.status_code == 404:
        raise RuntimeError(
            f"Recurso no encontrado en el backend (404, path={path}). "
            "Verifica que el customer_id sea DEMO-001 a DEMO-012."
        )
    if resp.status_code == 422:
        raise RuntimeError(f"Datos inválidos rechazados por el backend (422): {resp.text[:400]}")
    if not resp.is_success:
        raise RuntimeError(
            f"Error del backend (HTTP {resp.status_code}, path={path}): {resp.text[:200]}"
        )

    try:
        return resp.json()
    except Exception:
        raise RuntimeError(f"Respuesta no JSON del backend (path={path}).")


# ---------------------------------------------------------------------------
# Servidor MCP v2
# ---------------------------------------------------------------------------

mcp = MCPServer(
    name="banco-demo-mcp",
    version="1.0.0",
    instructions=(
        "Servidor MCP de Banco Demo — Créditos y Fraude. "
        "Todos los datos son SINTÉTICOS y solo para demostración. "
        "Clientes disponibles: DEMO-001 a DEMO-012. "
        "No ejecutes desembolsos reales ni consultes sistemas de producción."
    ),
)


# ---------------------------------------------------------------------------
# Herramienta 1: list_demo_customers
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Lista los 12 clientes sintéticos de demostración (DEMO-001 a DEMO-012) "
        "con datos financieros: ingresos, obligaciones, antigüedad, utilización "
        "de crédito y días de mora. "
        "Datos SIMULADOS — no representan personas reales. "
        "Úsala para explorar los clientes antes de consultar perfil, score o evaluar crédito."
    ),
)
async def list_demo_customers() -> dict[str, Any]:
    correlation_id = str(uuid.uuid4())
    try:
        return await _call_bank("GET", "/api/customers", correlation_id)
    except RuntimeError as e:
        return {"error": str(e), "tool": "list_demo_customers", "correlation_id": correlation_id}


# ---------------------------------------------------------------------------
# Herramienta 2: get_customer_credit_profile
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Devuelve el perfil crediticio de un cliente demo: datos financieros e "
        "historial de solicitudes previas (montos, fechas, resultados). "
        "Datos SINTÉTICOS. "
        "customer_id válidos: DEMO-001 a DEMO-012. "
        "Devuelve error si el cliente no existe."
    ),
)
async def get_customer_credit_profile(customer_id: str) -> dict[str, Any]:
    """
    Args:
        customer_id: Identificador del cliente demo (ej. DEMO-001, DEMO-012).
    """
    correlation_id = str(uuid.uuid4())
    try:
        safe_id = _safe_customer_id(customer_id)
        return await _call_bank(
            "GET", f"/api/customers/{safe_id}/profile", correlation_id
        )
    except RuntimeError as e:
        return {
            "error": str(e),
            "tool": "get_customer_credit_profile",
            "customer_id": customer_id,
            "correlation_id": correlation_id,
        }


# ---------------------------------------------------------------------------
# Herramienta 3: calculate_demo_credit_score
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Calcula el score de crédito SIMULADO de un cliente (rango 300–850). "
        "EXCLUSIVAMENTE DEMOSTRATIVO: no representa buró de crédito ni modelo validado. "
        "Devuelve score, desglose de factores (DTI, utilización, mora, antigüedad) "
        "y versión de reglas. "
        "status='insufficient_data' si ingresos == 0. "
        "status='not_found' si el cliente no existe."
    ),
)
async def calculate_demo_credit_score(customer_id: str) -> dict[str, Any]:
    """
    Args:
        customer_id: Identificador del cliente demo (ej. DEMO-001, DEMO-012).
    """
    correlation_id = str(uuid.uuid4())
    try:
        safe_id = _safe_customer_id(customer_id)
        return await _call_bank(
            "GET", f"/api/customers/{safe_id}/score", correlation_id
        )
    except RuntimeError as e:
        return {
            "error": str(e),
            "tool": "calculate_demo_credit_score",
            "customer_id": customer_id,
            "correlation_id": correlation_id,
        }


# ---------------------------------------------------------------------------
# Herramienta 4: check_demo_fraud_signals
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Evalúa señales de POSIBLE fraude sobre una solicitud entrante. "
        "Aplica 3 reglas deterministas sobre historial SINTÉTICO:\n"
        "  R1: ≥3 solicitudes del cliente en últimos 60 minutos.\n"
        "  R2: device_id asociado a múltiples clientes en el historial.\n"
        "  R3: monto > 5× ingresos mensuales del cliente.\n"
        "Niveles: HIGH (≥2 reglas), MEDIUM (1 regla), LOW (0 reglas).\n"
        "IMPORTANTE: Una alerta NO es prueba de fraude ni implica culpabilidad. "
        "Es un indicador que requiere revisión adicional."
    ),
)
async def check_demo_fraud_signals(
    customer_id: str,
    amount: float,
    device_id: str,
) -> dict[str, Any]:
    """
    Args:
        customer_id: Identificador del cliente demo (ej. DEMO-001).
        amount: Monto de la solicitud en COP. Debe ser mayor que 0.
        device_id: Identificador del dispositivo del solicitante.
                   Afecta a la regla R2 (dispositivo asociado a múltiples clientes).
                   Usar el device_id real del dispositivo.
    """
    correlation_id = str(uuid.uuid4())
    try:
        return await _call_bank(
            "POST",
            "/api/fraud/check",
            correlation_id,
            json_body={"customer_id": customer_id, "amount": amount, "device_id": device_id},
        )
    except RuntimeError as e:
        return {
            "error": str(e),
            "tool": "check_demo_fraud_signals",
            "customer_id": customer_id,
            "correlation_id": correlation_id,
        }


# ---------------------------------------------------------------------------
# Herramienta 5: evaluate_demo_loan_application
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Evalúa una solicitud de crédito SIMULADA combinando scoring, cuota y "
        "detección de fraude en una sola llamada. "
        "NO requiere invocar previamente las otras herramientas.\n\n"
        "Devuelve: decision, decision_code, motivos, cuota mensual estimada, "
        "total a pagar, carga financiera y señales de fraude.\n\n"
        "Prioridad de decisión:\n"
        "  1. not_found — cliente inexistente.\n"
        "  2. insufficient_data — ingresos == 0.\n"
        "  3. rejected — score < 500 O carga > 60 % (prioridad sobre fraude).\n"
        "  4. review_fraud_alert — aprobado crediticiamente pero alerta HIGH.\n"
        "  5. review — rango intermedio (score 500–649 o carga 40–60 %).\n"
        "  6. approved — score ≥ 650, carga ≤ 40 %, sin alerta HIGH.\n\n"
        "IMPORTANTE: Evaluación EXCLUSIVAMENTE DEMOSTRATIVA con datos sintéticos. "
        "No ejecuta desembolsos ni constituye oferta crediticia real."
    ),
)
async def evaluate_demo_loan_application(
    customer_id: str,
    amount: float,
    term_months: int,
    annual_effective_rate: float,
) -> dict[str, Any]:
    """
    Args:
        customer_id: Identificador del cliente demo (ej. DEMO-003, DEMO-010).
        amount: Monto solicitado en COP. Mayor que 0.
        term_months: Plazo en meses (1–360).
        annual_effective_rate: Tasa efectiva anual en decimal (ej. 0.18 para 18%).
                               Entre 0 y 2 (exclusivos).
    """
    correlation_id = str(uuid.uuid4())
    try:
        return await _call_bank(
            "POST",
            "/api/loans/evaluate",
            correlation_id,
            json_body={
                "customer_id": customer_id,
                "amount": amount,
                "term_months": term_months,
                "annual_effective_rate": annual_effective_rate,
            },
        )
    except RuntimeError as e:
        return {
            "error": str(e),
            "tool": "evaluate_demo_loan_application",
            "customer_id": customer_id,
            "correlation_id": correlation_id,
        }


# ---------------------------------------------------------------------------
# Aplicación FastAPI con middleware bearer y health check
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Banco Demo MCP arrancado. Backend: %s | Bearer: %s",
        BANK_API_BASE_URL,
        "activo" if MCP_BEARER_TOKEN else "inactivo (dev)",
    )
    async with mcp.session_manager.run():
        yield
    log.info("Banco Demo MCP apagado.")


fastapi_app = FastAPI(
    title="Banco Demo MCP Server",
    version="1.0.0",
    lifespan=lifespan,
)


@fastapi_app.middleware("http")
async def bearer_auth_middleware(request: Request, call_next):
    """
    Protege /mcp con bearer token.
    /health siempre accesible (probes de OpenShift y API Connect).
    """
    if request.url.path == "/health":
        return await call_next(request)

    if MCP_BEARER_TOKEN and request.url.path.startswith("/mcp"):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            log.warning(
                "Acceso rechazado a /mcp sin Bearer (src: %s)",
                request.headers.get("X-Forwarded-For", "?"),
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authorization: Bearer <token> requerido."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = auth_header.removeprefix("Bearer ").strip()
        if token != MCP_BEARER_TOKEN:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Bearer token inválido."},
                headers={"WWW-Authenticate": "Bearer"},
            )

    return await call_next(request)


@fastapi_app.get("/health")
async def health() -> dict[str, str]:
    """Health check para OpenShift y API Connect."""
    return {
        "status": "ok",
        "service": "banco-demo-mcp",
        "version": "1.0.0",
        "backend": BANK_API_BASE_URL,
    }


# Montar el transporte Streamable HTTP del servidor MCP en /mcp
fastapi_app.mount(
    "/mcp",
    app=mcp.streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=MCP_ALLOWED_HOSTS,
        ),
    ),
)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:fastapi_app",
        host=MCP_HOST,
        port=MCP_PORT,
        log_level="info",
    )
