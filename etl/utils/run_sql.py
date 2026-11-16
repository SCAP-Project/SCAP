"""Executa arquivos SQL em sequência no PostgreSQL.

Use --user para outro usuário e --dry-run para apenas exibir o SQL.
A senha vem do prompt ou de SQL_PASSWORD, nunca de argumento do shell."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

import psycopg2

from etl.config import get_logger, settings

log = get_logger(__name__)


def executar(caminhos: list[Path], usuario: str, senha: str) -> None:
    """Aplica os arquivos na mesma conexão, respeitando a ordem recebida."""
    log.info(
        "Conectando em %s:%s/%s como '%s'",
        settings.db_host,
        settings.db_port,
        settings.db_name,
        usuario,
    )

    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=usuario,
        password=senha,
        # Exige SSL na conexão ao RDS.
        sslmode="require",
    )
    # Cada arquivo SQL controla suas transações com BEGIN/COMMIT.
    conn.autocommit = True
    try:
        for caminho in caminhos:
            log.info("--- %s", caminho.name)
            del conn.notices[:]
            with conn.cursor() as cur:
                cur.execute(caminho.read_text(encoding="utf-8"))
                for aviso in conn.notices:
                    log.info("    %s", aviso.strip())
            log.info("    OK")
        log.info("Concluido: %d arquivo(s) aplicado(s)", len(caminhos))
    except Exception:
        log.exception("Falha ao aplicar %s", caminho.name)
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa arquivos .sql no banco do projeto"
    )
    parser.add_argument(
        "arquivos",
        type=Path,
        nargs="+",
        help="caminho(s) do .sql, aplicados na ordem informada",
    )
    parser.add_argument(
        "--user",
        default=settings.db_user,
        help=f"usuario do banco (padrao: {settings.db_user}, vindo do .env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="apenas exibe o conteudo dos arquivos, sem conectar",
    )
    args = parser.parse_args()

    caminhos = [a if a.is_absolute() else Path.cwd() / a for a in args.arquivos]
    faltando = [c for c in caminhos if not c.is_file()]
    if faltando:
        for c in faltando:
            log.error("Arquivo nao encontrado: %s", c)
        return 1

    if args.dry_run:
        for c in caminhos:
            print(f"{'=' * 70}\n-- {c}\n{'=' * 70}")
            print(c.read_text(encoding="utf-8"))
        return 0

    if args.user == settings.db_user:
        senha = settings.db_password
    else:
        senha = os.getenv("SQL_PASSWORD") or _pedir_senha(args.user)
        if not senha:
            return 1

    executar(caminhos, args.user, senha)
    return 0


def _pedir_senha(usuario: str, tentativas: int = 3) -> str:
    """Solicita uma senha não vazia, ignorando quebras de linha pendentes no terminal."""
    for _ in range(tentativas):
        senha = getpass.getpass(f"Senha de '{usuario}': ")
        if senha:
            return senha
        log.warning(
            "Senha vazia. Se voce colou um comando de varias linhas, o Enter "
            "sobrou no buffer -- digite a senha agora."
        )
    log.error("Senha vazia apos %d tentativas -- abortado", tentativas)
    return ""


if __name__ == "__main__":
    sys.exit(main())
