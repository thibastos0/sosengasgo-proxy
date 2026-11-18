# SOS Engasgo Proxy

Proxy serverless seguro para intermediar as requisições do aplicativo **SOS Engasgo** com workflows do [n8n](https://n8n.io/), hospedado na Vercel.

O proxy mantém as URLs e os tokens do n8n no ambiente do servidor, valida as requisições recebidas e encaminha apenas payloads JSON sanitizados.

## Endpoints

| Endpoint | Fluxo | Webhook configurado por |
| --- | --- | --- |
| `POST /api/ai` | Agente de IA | `N8N_AI_WEBHOOK_URL` |
| `POST /api/whatsapp` | WhatsApp | `N8N_WA_WEBHOOK_URL` |
| `POST /api/finishEmergency` | Finalização de emergência | `N8N_FINISH_WEBHOOK_URL` |

Todos os endpoints aceitam `POST` e `OPTIONS`. Outros métodos retornam `405 Method Not Allowed`.

## Requisitos

- Python 3.9 ou superior
- Uma conta/projeto na Vercel
- Workflows publicados no n8n
- Um token compartilhado entre o aplicativo e este proxy

## Configuração local

1. Clone o repositório e entre na pasta:

   ```bash
   git clone https://github.com/thibastos0/sosengasgo-proxy.git
   cd sosengasgo-proxy
   ```

2. Instale as dependências:

   ```bash
   pip install -e .
   ```

3. Configure as variáveis de ambiente. No desenvolvimento local, elas podem ser colocadas em um arquivo `.env`:

   ```env
   APP_VALIDATION_TOKEN=um-token-compartilhado-com-o-app
   ALLOWED_ORIGIN=https://sosengasgo.app

   N8N_AI_WEBHOOK_URL=https://n8n.exemplo.com/webhook/agente-ia
   N8N_AI_SECRET_TOKEN=token-do-workflow-de-ia

   N8N_WA_WEBHOOK_URL=https://n8n.exemplo.com/webhook/whatsapp
   N8N_WA_SECRET_TOKEN=token-do-workflow-do-whatsapp

   N8N_FINISH_WEBHOOK_URL=https://n8n.exemplo.com/webhook/finalizar-emergencia
   N8N_FINISH_SECRET_TOKEN=token-do-workflow-de-finalizacao
   ```

> Nunca versionar o arquivo `.env` ou tokens reais. As variáveis devem ser adicionadas como **Environment Variables** no projeto da Vercel.

## Deploy na Vercel

O `pyproject.toml` já declara os entrypoints das funções. Para publicar:

```bash
npx vercel
```

Para produção:

```bash
npx vercel --prod
```

Depois, configure todas as variáveis de ambiente no painel da Vercel ou com a CLI e faça um novo deploy.

## Autenticação e requisições

Cada `POST` precisa enviar:

- `Content-Type: application/json`
- `X-App-Local-Token` com o valor de `APP_VALIDATION_TOKEN`
- Um objeto JSON como corpo da requisição

Exemplo:

```bash
curl -X POST "https://seu-projeto.vercel.app/api/ai" \
  -H "Content-Type: application/json" \
  -H "X-App-Local-Token: um-token-compartilhado-com-o-app" \
  -d '{
    "message": "Como agir em caso de engasgo?",
    "session_id": "sessao-123"
  }'
```

O proxy encaminha o JSON ao webhook correspondente com:

- `Authorization: Bearer <N8N_*_SECRET_TOKEN>`
- `Content-Type: application/json`
- Redirecionamentos HTTP desabilitados
- Timeout de 10 segundos

As respostas JSON do n8n são repassadas ao aplicativo. Se o n8n retornar texto sem JSON válido, a resposta será encapsulada em `response_text`.

## Validações e segurança

O proxy:

- rejeita requisições sem o token do aplicativo (`401`);
- aceita somente JSON (`415`);
- limita o corpo a 2 MB (`413`);
- exige um objeto JSON na raiz;
- limita a profundidade do JSON a 5 níveis;
- limita listas e objetos a 50 itens/chaves;
- remove espaços nas extremidades de strings e rejeita caracteres nulos;
- impede cache e uso em frames por meio de headers de segurança;
- não expõe URLs, tokens ou detalhes internos do n8n nos erros;
- retorna `502 Bad Gateway` quando o n8n está indisponível ou retorna erro de servidor.

O valor padrão de `ALLOWED_ORIGIN` é `https://sosengasgo.app`. Defina essa variável apenas quando o frontend autorizado estiver em outra origem.

## Estrutura

```text
.
├── api/
│   ├── _shield.py          # Validação, sanitização e encaminhamento
│   ├── ai.py               # Endpoint /api/ai
│   ├── whatsapp.py         # Endpoint /api/whatsapp
│   └── finishEmergency.py  # Endpoint /api/finishEmergency
├── pyproject.toml          # Dependência e configuração da Vercel
└── .gitignore
```

## Licença

Este projeto é mantido para uso do SOS Engasgo. Consulte os responsáveis pelo projeto antes de reutilizar o código em outros produtos.
