"""Uso: python -m etl.csv_pipeline --generate"""

import argparse
from pathlib import Path

from .pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="ETL SCAP em CSV: raw -> trusted -> refined; sem AWS")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data")
    parser.add_argument("--generate", action="store_true", help="Regenera fontes sinteticas antes do ETL")
    parser.add_argument("--validate-only", action="store_true", help="Valida as fontes e transforma em memoria, sem substituir saidas")
    args = parser.parse_args()
    if args.generate and args.validate_only:
        parser.error("--generate grava fontes; use --validate-only separadamente")
    try:
        if args.generate:
            from .generate import generate_data
            print("Gerando CSVs sinteticos (seed=42)...", flush=True)
            generate_data(args.data_dir)
        manifest = run_pipeline(args.data_dir, validate_only=args.validate_only)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(1, f"ETL interrompido: {exc}\n")
    print("Validacao concluida." if args.validate_only else "ETL CSV concluido.")
    for table, count in manifest["counts"].items():
        print(f"  {table}: {count:,} linhas")
    if not args.validate_only:
        print(f"Arquivos: {args.data_dir.resolve()}")
        print("Manifesto: exports/etl_manifest.json")


if __name__ == "__main__":
    main()
