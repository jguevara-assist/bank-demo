# MCP interno consumido desde IBM API Connect

El gateway de API Connect y el MCP estan en el mismo cluster de OpenShift.
El manifiesto conserva el Service ClusterIP y no crea una Route para el MCP.

Backend del invoke de API Connect:

    http://banco-demo-mcp.demo-bank.svc.cluster.local:8080/mcp/

Usar la barra final para evitar la redireccion automatica. El Host enviado al
backend debe corresponder al Service interno, no al hostname publico de API Connect.
El transporte valida los hosts mediante MCP_ALLOWED_HOSTS; los valores por defecto
incluyen los DNS internos del Service en demo-bank. Si cambia el nombre del Service,
namespace o dominio del cluster, ajustar esa variable en el Deployment.

API Connect debe reemplazar Authorization por Bearer <MCP_BEARER_TOKEN> usando
su secreto de backend. No reenviar la credencial del consumidor como token interno.
Conservar Content-Type, Accept, MCP-Protocol-Version y Mcp-Session-Id en las
solicitudes y devolver Mcp-Session-Id en las respuestas. Mantener disponibles los
metodos del transporte MCP (POST, GET y DELETE) segun la politica del API.

## Aplicar en OpenShift

Desde la carpeta mcp_server:

    oc apply -f deploy/deployment.yaml -n demo-bank
    oc apply -f deploy/manifests.yaml -n demo-bank

Reconstruir y desplegar la imagen que incluye los cambios de server.py.
Eliminar la Route que ya existe es un paso separado: oc apply no elimina un
objeto que se retiro del manifiesto.

    oc delete route banco-demo-mcp -n demo-bank --ignore-not-found

Verificar que el Service tenga endpoints listos y que la Route ya no exista:

    oc get service banco-demo-mcp -n demo-bank
    oc get endpointslice -n demo-bank -l kubernetes.io/service-name=banco-demo-mcp
    oc get routes -n demo-bank

Probar initialize, tools/list y tools/call mediante la URL publicada por API Connect.
El endpoint /health interno solo comprueba el proceso, no la inicializacion MCP.

ClusterIP evita publicar el MCP fuera del cluster. El Bearer sigue siendo obligatorio
para /mcp. Para limitar tambien el acceso de otros pods se necesita una NetworkPolicy
con los labels y namespace reales de los gateways; este cambio no impone esa politica.
La API bancaria conserva su configuracion actual.
