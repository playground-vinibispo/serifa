r"""Envoltórios de LaTeX: \textbf{...} e parentes.

Operação de texto, sem widget: recebe o buffer e o comando, devolve nada e
mexe no buffer. Fica aqui porque a tabela de formatos é consultada em três
lugares -- os botões da barra, o submenu e os aceleradores -- e porque a
operação em si é a parte que dá para testar sem abrir janela.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

# (ação, comando LaTeX, ícone na barra ou None, rótulo no menu)
FORMATOS: list[tuple[str, str, str | None, str]] = [
    ("negrito", "textbf", "format-text-bold-symbolic", "Negrito"),
    ("italico", "textit", "format-text-italic-symbolic", "Itálico"),
    ("sublinhado", "underline", "format-text-underline-symbolic", "Sublinhado"),
    ("monoespaco", "texttt", None, "Monoespaçado"),
    ("enfase", "emph", None, "Ênfase"),
    ("citacao", "enquote", None, "Entre aspas"),
    ("nota", "footnote", None, "Nota de rodapé"),
]

# Só os dois que o mundo espera ganham atalho; os demais ficam no menu, para
# não atropelar mais teclas do vim do que o necessário.
ATALHOS = {"negrito": "<Control>b", "italico": "<Control>i"}


def envolver(buffer: Gtk.TextBuffer, comando: str) -> None:
    r"""Envolve a seleção em \comando{...}, ou abre as chaves no cursor."""
    abertura, fechamento = f"\\{comando}{{", "}"

    buffer.begin_user_action()
    # No PyGObject isto devolve (inicio, fim) havendo seleção e () sem --
    # não um booleano na frente, como a assinatura em C sugere.
    limites = buffer.get_selection_bounds()
    if limites:
        inicio, fim = limites
        selecionado = buffer.get_text(inicio, fim, True)
        marca = buffer.create_mark(None, inicio, True)
        buffer.delete(inicio, fim)
        onde = buffer.get_iter_at_mark(marca)
        buffer.insert(onde, f"{abertura}{selecionado}{fechamento}")
        buffer.delete_mark(marca)
    else:
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        dentro = cursor.get_offset() + len(abertura)
        # Inserido de uma vez: os pares automáticos só reagem a caractere
        # solto, então o } daqui não vira dois.
        buffer.insert(cursor, abertura + fechamento)
        buffer.place_cursor(buffer.get_iter_at_offset(dentro))
    buffer.end_user_action()
