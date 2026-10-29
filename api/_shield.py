from http.server import BaseHTTPRequestHandler
import hmac
import json
import logging
import os
from typing import Any
import requests

logger = logging.getLogger("sosengasgo.proxy")
logging.basicConfig(level=logging.INFO)

# MAX_PAYLOAD_BYTES = 64 * 1024  # 64 KB máximo
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024  # Aumentado para 2 MB para suportar áudio em Base64
MAX_JSON_DEPTH = 5
MAX_STRING_LENGTH = 2 * 1024 * 1024  # Aumentado para 2 MB para aceitar o áudio em Base64
REQUEST_TIMEOUT_SECONDS = 10


def sanitize_json_value(value: Any, depth: int = 0) -> Any:
    """Valida e sanitiza recursivamente o payload contra quebras e injeções."""
    if depth > MAX_JSON_DEPTH:
        raise ValueError("Profundidade máxima de JSON excedida.")

    if isinstance(value, dict):
        if len(value) > 50:
            raise ValueError("Número máximo de chaves excedido.")
        return {
            sanitize_json_value(str(k), depth + 1): sanitize_json_value(v, depth + 1)
            for k, v in value.items()
        }
    elif isinstance(value, list):
        if len(value) > 50:
            raise ValueError("Tamanho máximo de lista excedido.")
        return [sanitize_json_value(item, depth + 1) for item in value]
    elif isinstance(value, str):
        if "\x00" in value:
            raise ValueError("Caractere nulo inválido detectado.")
        cleaned = value.strip()
        if len(cleaned) > MAX_STRING_LENGTH:
            raise ValueError("Tamanho máximo de campo texto excedido.")
        return cleaned
    elif isinstance(value, (int, float, bool)) or value is None:
        return value
    else:
        raise ValueError("Tipo de dado JSON não suportado.")


class SecureN8NProxyHandler(BaseHTTPRequestHandler):
    """Classe base blindada para endpoints Serverless da Vercel."""

    ENV_WEBHOOK_URL: str = ""
    ENV_SECRET_TOKEN: str = ""

    # Silencia logs HTTP padrão que poderiam expor dados sensíveis
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _set_security_headers(self, status_code: int) -> None:
        allowed_origin = os.environ.get("ALLOWED_ORIGIN", "https://sosengasgo.app")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-App-Local-Token",
        )
        self.end_headers()

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        self._set_security_headers(status_code)
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _validate_app_token(self) -> bool:
        expected_token = os.environ.get("APP_VALIDATION_TOKEN", "")
        received_token = self.headers.get("X-App-Local-Token", "")
        if not expected_token or not received_token:
            return False
        return hmac.compare_digest(
            expected_token.encode("utf-8"),
            received_token.encode("utf-8"),
        )

    def do_OPTIONS(self) -> None:
        self._set_security_headers(204)

    def do_POST(self) -> None:
        try:
            # 1. Valida o token do App ANTES de ler o corpo da requisição
            if not self._validate_app_token():
                self._send_json(401, {"error": "Unauthorized"})
                return

            # 2. Exige Content-Type application/json
            content_type = self.headers.get("Content-Type", "")
            if not content_type.lower().startswith("application/json"):
                self._send_json(415, {"error": "Unsupported Media Type"})
                return

            # 3. Valida tamanho do corpo (Proteção contra DoS)
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json(400, {"error": "Bad Request"})
                return

            if content_length <= 0 or content_length > MAX_PAYLOAD_BYTES:
                self._send_json(413, {"error": "Payload Too Large or Empty"})
                return

            # 4. Decodifica e sanitiza o JSON
            raw_body = self.rfile.read(content_length)
            try:
                parsed_body = json.loads(raw_body.decode("utf-8"))
                if not isinstance(parsed_body, dict):
                    raise ValueError("A raiz do JSON deve ser um objeto.")
                sanitized_body = sanitize_json_value(parsed_body)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._send_json(400, {"error": "Invalid JSON payload"})
                return

            # 5. Carrega credenciais específicas do fluxo
            n8n_url = os.environ.get(self.ENV_WEBHOOK_URL, "").strip()
            n8n_token = os.environ.get(self.ENV_SECRET_TOKEN, "").strip()

            if not n8n_url or not n8n_token:
                logger.error(
                    "Configuração de ambiente ausente para %s",
                    self.ENV_WEBHOOK_URL,
                )
                self._send_json(500, {"error": "Internal Server Error"})
                return

            # 6. Encaminha ao n8n de forma isolada
            upstream_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {n8n_token}",
                "User-Agent": "SOSEngasgo-Vercel-Shield/1.0",
            }

            n8n_response = requests.post(
                n8n_url,
                json=sanitized_body,
                headers=upstream_headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,
            )

            # 7. Mascara falhas internas do n8n para não expor o backend
            if n8n_response.status_code >= 500:
                logger.error(
                    "n8n upstream retornou status %d",
                    n8n_response.status_code,
                )
                self._send_json(502, {"error": "Bad Gateway"})
                return

            # Garante que a resposta repassada ao App seja sempre JSON válido
            try:
                response_json = n8n_response.json()
            except ValueError:
                response_json = {"status": "ok"}

            self._send_json(n8n_response.status_code, response_json)

        except requests.RequestException:
            # Nunca vaza URL/Host do n8n em falhas de conexão ou timeout
            logger.error("Falha de comunicação com o upstream n8n.")
            self._send_json(502, {"error": "Bad Gateway"})
        except Exception:
            logger.error("Erro inesperado no processamento do proxy.")
            self._send_json(500, {"error": "Internal Server Error"})

    # Bloqueio estrito de qualquer método que não seja POST ou OPTIONS
    def _method_not_allowed(self) -> None:
        self._send_json(405, {"error": "Method Not Allowed"})

    do_GET = _method_not_allowed
    do_PUT = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_HEAD = _method_not_allowed

