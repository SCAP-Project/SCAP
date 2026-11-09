"""Executa geradores existentes em workspace temporario e publica os CSVs."""

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import tempfile


GENERATORS = Path(__file__).resolve().parents[1] / "data_generation/generators"


def generate_data(data_dir: Path):
    """Ordem: transacoes -> liquidacoes -> parceiros derivados do historico.

    Nenhum gerador precisa importar settings, carregar .env ou abrir conexao.
    A pasta temporaria impede publicar uma geracao que falhou pela metade.
    """
    data_dir = data_dir.resolve()
    previous_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="scap-generation-") as directory:
        workspace = Path(directory).resolve()
        (workspace / "sql").mkdir()
        log = io.StringIO()
        try:
            os.chdir(workspace)
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                notebook = json.loads((GENERATORS / "dados_transacoes_financeiras.ipynb").read_text(encoding="utf-8"))
                namespace = {"display": lambda *args, **kwargs: None}
                for index, cell in enumerate(notebook["cells"]):
                    if cell["cell_type"] == "code":
                        exec(compile("".join(cell["source"]), f"transacoes_cell_{index}", "exec"), namespace)
                for entity in ["areas", "categorias_contabeis", "funcionarios", "pagamentos", "recebimentos", "fornecedores_clientes"]:
                    runpy.run_path(str(GENERATORS / f"dados_raw_{entity}.py"))
        finally:
            os.chdir(previous_cwd)
        for source in sorted((workspace / "data").rglob("*.csv")):
            target = data_dir / source.relative_to(workspace / "data")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        exports = data_dir / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        (exports / "generation.log").write_text(log.getvalue(), encoding="utf-8")
