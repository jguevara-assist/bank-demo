FROM python:3.12-slim

# Usuario no-root para compatibilidad con OpenShift (UID arbitrario)
RUN groupadd -r mcpuser && useradd -r -g mcpuser mcpuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# OpenShift puede asignar cualquier UID; el directorio debe ser escribible
RUN chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8080

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8080 \
    REQUEST_TIMEOUT=15

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["python", "server.py"]
