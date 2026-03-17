#!/usr/bin/env python
"""
Cria um usuário administrador inicial no banco de dados.

Uso:
    python scripts/create_admin.py
    python scripts/create_admin.py --name "João" --email "admin@exemplo.com" --password "s3cret"

Se os argumentos não forem passados, o script solicita interativamente.
"""
import argparse
import sys
from pathlib import Path

# garante que o package 'app' é encontrado independente de onde o script é chamado
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from app.db.session import SessionLocal
from app.db.models import User
from app.core.security import hash_password


def _prompt(label: str, secret: bool = False) -> str:
    import getpass
    fn = getpass.getpass if secret else input
    while True:
        value = fn(f"{label}: ").strip()
        if value:
            return value
        print("  ✗ Campo obrigatório, tente novamente.")


def create_admin(name: str, email: str, password: str) -> None:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"  ⚠  Usuário com e-mail '{email}' já existe (role={existing.role}).")
            return

        admin = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"  ✓  Admin criado com sucesso! id={admin.id}  email={admin.email}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria usuário admin inicial")
    parser.add_argument("--name",     default=None)
    parser.add_argument("--email",    default=None)
    parser.add_argument("--password", default=None)
    args = parser.parse_args()

    print("\n=== Criação do usuário administrador ===\n")
    name     = args.name     or _prompt("Nome completo")
    email    = args.email    or _prompt("E-mail")
    password = args.password or _prompt("Senha", secret=True)

    create_admin(name, email, password)


if __name__ == "__main__":
    main()
