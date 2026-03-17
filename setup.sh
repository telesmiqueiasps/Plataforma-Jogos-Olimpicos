#!/usr/bin/env bash
# =============================================================================
# setup.sh — Configuração do ambiente local para o sports-platform
#
# Uso:
#   chmod +x setup.sh
#   ./setup.sh
#
# Para pular a criação do admin (ex.: em CI):
#   SKIP_ADMIN=true ./setup.sh
# =============================================================================

set -euo pipefail

# ---- cores ----
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[setup]${NC} $*"; }
warn()    { echo -e "${YELLOW}[aviso]${NC} $*"; }
error()   { echo -e "${RED}[erro]${NC} $*" >&2; exit 1; }

BACKEND_DIR="$(cd "$(dirname "$0")/backend" && pwd)"
VENV_DIR="$BACKEND_DIR/.venv"
PYTHON="${PYTHON:-python3}"

# ---------------------------------------------------------------------------
# 1. Verifica Python
# ---------------------------------------------------------------------------
info "Verificando Python..."
$PYTHON --version 2>&1 | grep -qE "3\.(10|11|12)" \
  || warn "Python 3.10+ recomendado. Versão encontrada: $($PYTHON --version 2>&1)"

# ---------------------------------------------------------------------------
# 2. Cria virtualenv
# ---------------------------------------------------------------------------
if [ -d "$VENV_DIR" ]; then
  warn "Virtualenv já existe em $VENV_DIR — pulando criação."
else
  info "Criando virtualenv em $VENV_DIR..."
  $PYTHON -m venv "$VENV_DIR"
fi

# ativa o venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Virtualenv ativado: $(which python)"

# ---------------------------------------------------------------------------
# 3. Instala dependências
# ---------------------------------------------------------------------------
info "Instalando dependências..."
pip install --upgrade pip --quiet
pip install -r "$BACKEND_DIR/requirements.txt" --quiet
info "Dependências instaladas."

# ---------------------------------------------------------------------------
# 4. Cria .env se não existir
# ---------------------------------------------------------------------------
ENV_FILE="$BACKEND_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  info "Criando $ENV_FILE a partir de .env.example..."
  cp "$BACKEND_DIR/.env.example" "$ENV_FILE"

  # gera SECRET_KEY aleatória automaticamente
  SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|TROQUE-POR-UMA-CHAVE-SECRETA-FORTE-DE-64-CARACTERES|$SECRET|" "$ENV_FILE"
  else
    sed -i "s|TROQUE-POR-UMA-CHAVE-SECRETA-FORTE-DE-64-CARACTERES|$SECRET|" "$ENV_FILE"
  fi

  warn "Arquivo .env criado. Preencha DATABASE_URL antes de continuar."
  warn "Pressione ENTER quando estiver pronto, ou Ctrl+C para cancelar."
  read -r
else
  info ".env já existe — mantendo."
fi

# ---------------------------------------------------------------------------
# 5. Verifica conexão com o banco antes de rodar migrations
# ---------------------------------------------------------------------------
info "Verificando conexão com o banco de dados..."
cd "$BACKEND_DIR"
python - <<'EOF'
import os, sys
from dotenv import load_dotenv
load_dotenv()
url = os.environ.get("DATABASE_URL", "")
if not url or "user:password" in url:
    print("  DATABASE_URL não configurada ou com valor padrão.")
    sys.exit(1)

import sqlalchemy as sa
try:
    engine = sa.create_engine(url, connect_args={"connect_timeout": 5})
    with engine.connect() as conn:
        conn.execute(sa.text("SELECT 1"))
    print("  Conexão OK.")
except Exception as e:
    print(f"  Falha na conexão: {e}")
    sys.exit(1)
EOF

# ---------------------------------------------------------------------------
# 6. Roda migrations com Alembic
# ---------------------------------------------------------------------------
info "Rodando alembic upgrade head..."
alembic upgrade head
info "Migrations aplicadas."

# ---------------------------------------------------------------------------
# 7. Cria usuário admin inicial
# ---------------------------------------------------------------------------
if [ "${SKIP_ADMIN:-false}" = "true" ]; then
  warn "SKIP_ADMIN=true — pulando criação do admin."
else
  info "Criando usuário administrador inicial..."
  python scripts/create_admin.py
fi

# ---------------------------------------------------------------------------
# Concluído
# ---------------------------------------------------------------------------
echo ""
info "=============================================="
info " Setup concluído!"
info " Para iniciar o servidor:"
info "   cd backend && source .venv/bin/activate"
info "   uvicorn app.main:app --reload"
info " Documentação da API: http://localhost:8000/docs"
info "=============================================="
