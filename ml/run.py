"""Execucao por arquivos/etapas: python -m ml.run --stage all."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="SCAP ML: EDA e deteccao temporal de anomalias")
    parser.add_argument("--stage", choices=["features", "split", "train", "evaluate", "notebooks", "all"], default="all")
    args = parser.parse_args()
    from .experiment import prepare_features, prepare_split, train, evaluate_test
    from .results import write_summary
    if args.stage in ["features", "all"]:
        prepare_features()
    if args.stage in ["split", "all"]:
        prepare_split()
    if args.stage in ["train", "all"]:
        train()
    if args.stage in ["evaluate", "all"]:
        evaluate_test()
        write_summary()
    if args.stage in ["notebooks", "all"]:
        from .notebooks import build_notebooks, execute_notebooks
        # Os notebooks de etapas executam novamente cada passo; isso verifica
        # que funcionam com kernels novos, sem variaveis de sessoes anteriores.
        execute_notebooks(build_notebooks())
    print("Etapa concluida.")


if __name__ == "__main__":
    main()
