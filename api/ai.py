from ._shield import SecureN8NProxyHandler


class handler(SecureN8NProxyHandler):
    """Endpoint Serverless para o fluxo do Agente IA (/api/ai)."""

    ENV_WEBHOOK_URL = "N8N_AI_WEBHOOK_URL"
    ENV_SECRET_TOKEN = "N8N_AI_SECRET_TOKEN"