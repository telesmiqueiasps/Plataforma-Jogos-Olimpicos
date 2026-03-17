# Sports Platform

Plataforma de gerenciamento de campeonatos esportivos olímpicos escolares.
Backend FastAPI + PostgreSQL · Frontend HTML/JS estático.

---

## Sumário

- [Arquitetura](#arquitetura)
- [Desenvolvimento local](#desenvolvimento-local)
- [Deploy no Render (backend + banco)](#deploy-no-render)
- [Deploy no Netlify (frontend)](#deploy-no-netlify)
- [Conectar frontend ao backend](#conectar-frontend-ao-backend)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Comandos úteis](#comandos-úteis)

---

## Arquitetura

```
┌─────────────────────┐        HTTPS          ┌──────────────────────┐
│   Netlify (CDN)     │ ─────────────────────▶ │  Render Web Service  │
│   frontend/         │    REST JSON API        │  FastAPI / Uvicorn   │
│   HTML + JS puro    │                         │  backend/            │
└─────────────────────┘                         └──────────┬───────────┘
                                                           │ SQLAlchemy
                                                ┌──────────▼───────────┐
                                                │  Render PostgreSQL   │
                                                │  (free tier)         │
                                                └──────────────────────┘
```

---

## Desenvolvimento local

### Pré-requisitos

- Python 3.10+
- PostgreSQL 14+ rodando localmente (ou URL de um banco remoto)
- Git

### Setup automático

```bash
git clone <url-do-repositorio>
cd "Plataforma Jogos Olimpicos"

chmod +x setup.sh
./setup.sh
```

O script `setup.sh`:
1. Cria o virtualenv em `backend/.venv`
2. Instala todas as dependências do `requirements.txt`
3. Cria o `backend/.env` com `SECRET_KEY` gerada automaticamente
4. Verifica a conexão com o banco
5. Roda `alembic upgrade head`
6. Cria o primeiro usuário administrador (interativo)

### Setup manual (passo a passo)

```bash
cd backend

# 1. Virtualenv
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Dependências
pip install -r requirements.txt

# 3. Variáveis de ambiente
cp .env.example .env
# Edite .env e preencha DATABASE_URL e SECRET_KEY

# 4. Migrations
alembic upgrade head

# 5. Admin inicial
python scripts/create_admin.py

# 6. Servidor
uvicorn app.main:app --reload
```

Acesse:
- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- Frontend: abra `frontend/index.html` no browser (ou use Live Server no VSCode)

---

## Deploy no Render

### Opção A — Blueprint automático (recomendado)

O arquivo `render.yaml` na raiz do repositório define tudo automaticamente.

1. Acesse <https://dashboard.render.com> e clique em **New → Blueprint**
2. Conecte o repositório GitHub
3. O Render detecta o `render.yaml` e cria:
   - Serviço web `sports-platform-api`
   - Banco `sports-platform-db` (PostgreSQL free)
4. Aguarde o build (~3 min na primeira vez)
5. Copie a URL do serviço (ex: `https://sports-platform-api.onrender.com`)

### Opção B — Manual

#### 1. Crie o banco PostgreSQL

1. Dashboard → **New → PostgreSQL**
2. Nome: `sports-platform-db` · Plano: Free · Região: Oregon
3. Aguarde ficar **Available**
4. Copie a **Internal Database URL** (usada pelo serviço web)

#### 2. Crie o serviço web

1. Dashboard → **New → Web Service**
2. Conecte o repositório
3. Configure:

   | Campo | Valor |
   |---|---|
   | **Root Directory** | `backend` |
   | **Runtime** | Python 3 |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | **Pre-Deploy Command** | `alembic upgrade head` |

4. Na aba **Environment**, adicione as variáveis:

   | Chave | Valor |
   |---|---|
   | `DATABASE_URL` | Cole a **Internal Database URL** do passo 1 |
   | `SECRET_KEY` | Clique em **Generate** ou use `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `ALLOWED_ORIGINS` | URL do frontend no Netlify (preencha após o deploy do frontend) |
   | `ALGORITHM` | `HS256` |
   | `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` |

5. Clique em **Create Web Service**

#### 3. Crie o admin no Render

Após o primeiro deploy bem-sucedido, abra o **Shell** do serviço no Render e execute:

```bash
python scripts/create_admin.py --name "Admin" --email "admin@exemplo.com" --password "suasenha"
```

---

## Deploy no Netlify

### Opção A — Interface web

1. Acesse <https://app.netlify.com> e clique em **Add new site → Import from Git**
2. Conecte o repositório GitHub
3. Configure:

   | Campo | Valor |
   |---|---|
   | **Base directory** | *(vazio)* |
   | **Build command** | *(vazio — site estático)* |
   | **Publish directory** | `frontend` |

4. Clique em **Deploy site**
5. Após o deploy, copie a URL (ex: `https://sports-platform-abc123.netlify.app`)

> O arquivo `netlify.toml` já está configurado na raiz — o Netlify o detecta automaticamente com o redirect SPA e os headers de segurança.

### Opção B — Netlify CLI

```bash
npm install -g netlify-cli
netlify login
netlify init          # selecione o repositório
netlify deploy --prod
```

---

## Conectar frontend ao backend

Após ter as duas URLs, você precisa fazer **duas configurações**:

### 1. Atualizar a URL da API no frontend

Edite [frontend/js/api.js](frontend/js/api.js), linha 1:

```js
// Troque localhost pela URL real do Render
const API_BASE = "https://sports-platform-api.onrender.com/api";
```

Faça commit e push — o Netlify faz redeploy automático.

### 2. Liberar o CORS no backend (Render)

No painel do Render → serviço `sports-platform-api` → **Environment**:

```
ALLOWED_ORIGINS = https://sports-platform-abc123.netlify.app
```

Salve. O Render reinicia o serviço automaticamente.

> Para múltiplos domínios (ex: preview + produção):
> ```
> ALLOWED_ORIGINS = https://sports-platform.netlify.app,https://seu-dominio.com
> ```

---

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | Sim | URL de conexão PostgreSQL |
| `SECRET_KEY` | Sim | Chave de assinatura JWT (min. 32 chars aleatórios) |
| `ALLOWED_ORIGINS` | Sim em produção | Origens CORS separadas por vírgula |
| `ALGORITHM` | Não | Algoritmo JWT (padrão: `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Não | Expiração do token (padrão: `60`) |
| `APP_NAME` | Não | Nome da aplicação (padrão: `Sports Platform`) |
| `DEBUG` | Não | Modo debug (padrão: `False`) |

---

## Comandos úteis

```bash
# Gerar nova migration após alterar models.py
alembic revision --autogenerate -m "descricao da mudanca"
alembic upgrade head

# Reverter última migration
alembic downgrade -1

# Ver histórico de migrations
alembic history --verbose

# Rodar servidor com reload automático
uvicorn app.main:app --reload --port 8000

# Criar admin (qualquer ambiente)
python scripts/create_admin.py

# Verificar sintaxe de todos os arquivos Python
python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('app').rglob('*.py')]"
```

---

## Estrutura do projeto

```
.
├── render.yaml              # deploy automático Render (backend + banco)
├── netlify.toml             # deploy automático Netlify (frontend)
├── setup.sh                 # setup do ambiente local
│
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, CORS, routers
│   │   ├── api/
│   │   │   ├── deps.py      # get_current_user, require_admin
│   │   │   └── routes/      # auth, users, sports
│   │   ├── core/
│   │   │   ├── config.py    # Settings (pydantic-settings + .env)
│   │   │   └── security.py  # bcrypt, JWT
│   │   ├── db/
│   │   │   ├── models.py    # User, Sport, Team, Athlete, Championship…
│   │   │   └── session.py   # engine sync + async (asyncpg)
│   │   ├── schemas/         # Pydantic I/O schemas
│   │   └── services/
│   │       ├── user_service.py
│   │       └── standings_service.py  # classificação, calendário, suspensões
│   ├── alembic/             # migrations
│   ├── scripts/
│   │   └── create_admin.py
│   ├── requirements.txt
│   ├── Procfile
│   └── .env.example
│
└── frontend/
    ├── index.html           # dashboard principal
    ├── login.html
    ├── register.html
    ├── css/style.css
    └── js/
        ├── api.js           # wrapper fetch + token JWT
        └── auth.js          # formulários login/register
```
