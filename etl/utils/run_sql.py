"""Executa um arquivo .sql no banco, opcionalmente como outro usuario.

Existe porque nem toda maquina do time tem o cliente `psql` instalado -- este
script usa o psycopg2 que ja vem no requirements.txt. Util principalmente para
DDL e migracoes, que exigem o usuario MASTER (scap_admin): as tabelas pertencem
a ele, e o svc_etl do .env so tem DML (grupo app_etl).

A senha nunca vem por argumento de linha de comando (ficaria no historico do
shell): ou e digitada no prompt, ou vem da variavel de ambiente SQL_PASSWORD.

Uso:
    # como o usuario do .env (svc_etl)
    python -m etl.utils.run_sql sql/ddl/00_create_schemas.sql

    # como outro usuario -- pede a senha no prompt
    python -m etl.utils.run_sql sql/migrations/2026_08_15_fase_b.sql --user scap_admin

    # varios arquivos na ordem, na mesma conexao
    python -m etl.utils.run_sql sql/ddl/02_create_trusted_tables.sql \\
                                sql/ddl/03_create_refined_tables.sql --user scap_admin

    # so mostra o que seria executado, sem tocar no banco
    python -m etl.utils.run_sql sql/ddl/05_create_ml_tables.sql --dry-run
"""

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
    """Aplica os arquivos em sequencia, na mesma conexao.

    Varios arquivos numa chamada so importam quando um depende do outro --
    dropar e recriar as camadas, por exemplo, tem que acontecer na ordem certa
    e sem janela entre os passos.
    """
    log.info("Conectando em %s:%s/%s como '%s'",
             settings.db_host, settings.db_port, settings.db_name, usuario)

    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=usuario,
        password=senha,
        # RDS exige SSL. Sem isso, sslmode='prefer' (padrao do libpq) tenta a
        # conexao SSL e, se falhar por qualquer motivo, tenta de novo sem SSL --
        # e o pg_hba do RDS rejeita a segunda tentativa por falta de
        # criptografia, poluindo o erro real com uma mensagem secundaria.
        sslmode="require",
    )
    # autocommit para o proprio arquivo controlar as transacoes (BEGIN/COMMIT).
    conn.autocommit = True
    try:
        for caminho in caminhos:
            log.info("--- %s", caminho.name)
            del conn.notices[:]
            with conn.cursor() as cur:
                cur.execute(caminho.read_text(encoding="utf-8"))
                # NOTICE do servidor ("already exists, skipping", RAISE NOTICE...)
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
    parser = argparse.ArgumentParser(description="Executa arquivos .sql no banco do projeto")
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
    """Pede a senha no prompt, tolerando linhas vazias no buffer do stdin.

    Colar um comando multi-linha no PowerShell deixa o newline final no buffer;
    o getpass seguinte le esse newline e devolve string vazia. Em vez de abortar
    (o que obriga a redigitar o comando inteiro), simplesmente perguntamos de novo.
    """
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
