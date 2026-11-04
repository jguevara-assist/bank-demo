# Banco Demo — Créditos y Fraude

> **ADVERTENCIA:** Esta aplicación utiliza exclusivamente datos sintéticos con fines demostrativos.  
> **No utilizar para decisiones crediticias reales.**

---

## Descripción

Servicio Python FastAPI que expone:

- **API REST** con 5 endpoints documentados (OpenAPI).
- **Interfaz web en español** — una sola página, sin frameworks frontend.
- Datos JSON locales con semilla reproducible (12 clientes ficticios, identificadores `DEMO-001` a `DEMO-012`).

---

## Requisitos previos

- Python 3.12+  
- (Opcional) Docker y Docker Compose para ejecución en contenedor.

---

## Ejecución local (sin Docker)

```bash
cd banco_demo
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Abre en el navegador:

| Recurso            | URL                              |
|--------------------|----------------------------------|
| Interfaz web       | http://localhost:8000/           |
| OpenAPI (Swagger)  | http://localhost:8000/docs       |
| ReDoc              | http://localhost:8000/redoc      |

---

## Ejecución con Docker Compose

```bash
cd banco_demo
docker compose up --build
```

Los mismos URLs aplican: `http://localhost:8000/`.

---

## Endpoints API

| Método | Ruta                                        | operationId                     |
|--------|---------------------------------------------|---------------------------------|
| GET    | `/api/customers`                            | `list_demo_customers`           |
| GET    | `/api/customers/{customer_id}/profile`      | `get_customer_credit_profile`   |
| GET    | `/api/customers/{customer_id}/score`        | `calculate_demo_credit_score`   |
| POST   | `/api/fraud/check`                          | `check_demo_fraud_signals`      |
| POST   | `/api/loans/evaluate`                       | `evaluate_demo_loan_application`|

---

## Fórmula del score de crédito (v1.0)

```
score = 300 + composite × 550
```

Donde `composite` (rango 0–1) es:

```
composite = 0.35 × P_dti + 0.30 × P_util + 0.25 × P_mora + 0.10 × P_hist
```

### Puntuaciones parciales

| Factor            | Fórmula                                                        |
|-------------------|----------------------------------------------------------------|
| `P_dti`           | `max(0, 1 − obligations / income)` (máx. DTI = 100%)          |
| `P_util`          | `max(0, 1 − credit_utilization)`                               |
| `P_mora`          | 1.0 si mora = 0 d · 0.5 si mora ≤ 30 d · 0.25 si ≤ 60 d · 0.0 si > 60 d |
| `P_hist`          | `min(1, history_months / 120)`                                 |

Si `monthly_income == 0` → estado `insufficient_data`.

---

## Reglas de decisión de crédito (v1.0)

| Decisión               | Condición                                           |
|------------------------|-----------------------------------------------------|
| `approved`             | score ≥ 650 **y** nueva carga financiera ≤ 40%      |
| `rejected`             | score < 500 **o** carga > 60%                       |
| `review`               | demás casos                                         |
| `review_fraud_alert`   | aprobado crediticiamente pero alerta de fraude HIGH |
| `insufficient_data`    | ingresos == 0                                       |

---

## Reglas de detección de fraude (v1.0)

| ID | Nombre                  | Condición                                                              |
|----|-------------------------|------------------------------------------------------------------------|
| R1 | `MULTIPLE_REQUESTS`     | ≥ 3 solicitudes del mismo cliente en los últimos 60 minutos            |
| R2 | `DEVICE_MULTI_CLIENT`   | Dispositivo asociado a ≥ 2 clientes distintos en el historial          |
| R3 | `UNUSUAL_AMOUNT`        | Monto > 5× los ingresos mensuales                                      |

**Niveles:** `HIGH` (≥ 2 reglas) → revisión automática · `MEDIUM` (1 regla) · `LOW` (0 reglas).  
Una alerta NO constituye prueba de fraude.

---

## Ejemplos de casos reproducibles

### Caso 1 — Aprobación (DEMO-003)

```bash
curl -X POST http://localhost:8000/api/loans/evaluate \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-003","amount":20000000,"term_months":36,"annual_effective_rate":0.18}'
```

Esperado: `decision = "approved"` (score alto, carga baja).

### Caso 2 — Rechazo (DEMO-010)

```bash
curl -X POST http://localhost:8000/api/loans/evaluate \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-010","amount":5000000,"term_months":24,"annual_effective_rate":0.18}'
```

Esperado: `decision = "rejected"` (score muy bajo, carga > 60%).

### Caso 3 — Información insuficiente (DEMO-012)

```bash
curl -X GET http://localhost:8000/api/customers/DEMO-012/score
```

Esperado: `status = "insufficient_data"`.

### Caso 4 — Revisión por alerta de fraude (DEMO-001)

```bash
curl -X POST http://localhost:8000/api/fraud/check \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"DEMO-001","amount":15000000,"device_id":"DEV-AAA"}'
```

Esperado: `alert_level = "HIGH"` (R1 + R2 activas).

---

## Pruebas

```bash
cd banco_demo
pip install pytest
pytest tests/ -v
```

Cobertura mínima:
- Cálculo determinista de cuota fija.
- Score correcto para clientes con datos completos.
- `insufficient_data` para DEMO-012.
- Alerta `HIGH` para DEMO-001.

---

## Limitaciones

- Score exclusivamente demostrativo. No representa ningún buró de crédito ni modelo estadístico validado.
- Sin autenticación ni controles de acceso.
- Datos en memoria; no persiste solicitudes nuevas.
- No conecta a servicios externos, IA ni bases de datos.
