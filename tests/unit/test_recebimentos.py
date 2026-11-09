"""Regressao do parcelamento, executando os dois geradores com CSVs locais."""

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest

import pandas as pd


GENERATORS = Path(__file__).resolve().parents[2] / "etl/data_generation/generators"


class ParcelamentoTest(unittest.TestCase):
    def test_parcelas_somam_valor_liquido_no_script_e_no_notebook(self):
        for suffix in (".py", ".ipynb"):
            with self.subTest(formato=suffix), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory).resolve()
                (workspace / "sql").mkdir()
                origem = workspace / "data/raw/transacoes_financeiras"
                origem.mkdir(parents=True)
                transacoes = pd.DataFrame([
                    {
                        "id_transacao_raw": f"TR-{i:05d}",
                        "data_transacao": "2025-01-10",
                        "valor_liquido": 100.01 + i,
                        "forma_pagamento": "PIX",
                        "tipo_transacao": "RECEITA",
                        "status_pagamento": "PAGO",
                    }
                    for i in range(20)
                ])
                transacoes.to_csv(origem / "transacoes.csv", index=False)
                previous = Path.cwd()
                try:
                    os.chdir(workspace)
                    with contextlib.redirect_stdout(io.StringIO()):
                        path = GENERATORS / f"dados_raw_recebimentos{suffix}"
                        if suffix == ".py":
                            runpy.run_path(str(path))
                        else:
                            notebook = json.loads(path.read_text(encoding="utf-8"))
                            namespace = {}
                            for cell in notebook["cells"]:
                                if cell["cell_type"] == "code":
                                    exec("".join(cell["source"]), namespace)
                finally:
                    os.chdir(previous)

                recebimentos = pd.read_csv(workspace / "data/raw/recebimentos/recebimentos.csv")
                totais = recebimentos.groupby("id_transacao_raw")["valor_recebido"].agg(["sum", "size"])
                self.assertEqual(int((totais["size"] == 2).sum()), 3)
                self.assertTrue((recebimentos["valor_recebido"] > 0).all())
                esperados = transacoes.set_index("id_transacao_raw")["valor_liquido"]
                for identifier, row in totais.iterrows():
                    self.assertEqual(round(row["sum"] * 100), round(esperados[identifier] * 100))


if __name__ == "__main__":
    unittest.main()
