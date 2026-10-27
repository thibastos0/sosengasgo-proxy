try:
    from api._shield import SecureN8NProxyHandler
except ImportError:
    from _shield import SecureN8NProxyHandler


class handler(SecureN8NProxyHandler):
    """Endpoint Serverless para o fluxo do WhatsApp (/api/whatsapp)."""

    ENV_WEBHOOK_URL = "N8N_WA_WEBHOOK_URL"
    ENV_SECRET_TOKEN = "N8N_WA_SECRET_TOKEN"

