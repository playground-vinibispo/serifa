"""O que a janela lembra entre uma abertura e outra.

Arquivo pequeno de propósito: é o único estado que sobrevive ao fechamento, e
deixá-lo perdido no meio da janela tornava difícil ver o que exatamente é
persistido -- e difícil desviar em teste, que era feito remendando uma
variável de módulo.
"""

from __future__ import annotations

import json
from pathlib import Path

from gi.repository import GLib

PADRAO = Path(GLib.get_user_config_dir()) / "serifa" / "estado.json"


def ler(caminho: Path) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def gravar(caminho: Path, dados: dict) -> None:
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    except OSError:
        pass   # sessão é conveniência; falhar aqui não pode atrapalhar nada
