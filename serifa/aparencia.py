r"""Tipografia e medida da coluna de texto.

**Cores não entram aqui.** Houve uma tentativa de impor uma paleta de papel,
com a marcação LaTeX recuada e a prosa em tinta cheia; foi revertida a pedido
do usuário, que prefere o esquema padrão do GtkSourceView. Paleta é gosto de
quem escreve, e quem escreve já escolheu.

O que sobrou é o que não é gosto: isto não é um editor de código. Número de
linha, régua de 80 colunas e realce da linha atual são instrumentos de quem
navega por endereço, não de quem lê um argumento de cem palavras. E a coluna
é limitada, porque linha longa cansa a leitura -- o limite de uma página do
professor é justamente sobre ler.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk

FONTE = "JetBrainsMono NF"
CORPO = 11.5
MEDIDA = 74          # caracteres por linha
MARGEM_MINIMA = 24
ENTRELINHA = 6       # pixels somados acima e abaixo de cada linha

CSS = f"""
/* Só tipografia. As cores vêm do esquema do GtkSourceView, que é escolha do
   usuário. */
textview.serifa-editor {{
    font-family: "{FONTE}", "Red Hat Mono", monospace;
    font-size: {CORPO}pt;
}}
.serifa-estado {{
    font-size: 0.85em;
}}
"""


def instalar_css() -> None:
    provedor = Gtk.CssProvider()
    provedor.load_from_string(CSS)
    tela = Gdk.Display.get_default()
    if tela is not None:
        Gtk.StyleContext.add_provider_for_display(
            tela, provedor, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def largura_do_caractere(widget: Gtk.Widget) -> int:
    """Largura de um caractere na fonte do editor, em pixels."""
    contexto = widget.get_pango_context()
    metrica = contexto.get_metrics(contexto.get_font_description(), None)
    return max(1, metrica.get_approximate_char_width() // 1024)


def margem_para(largura: int, largura_do_char: int) -> int:
    """Margem lateral que centra uma coluna de MEDIDA caracteres.

    Função pura para poder ser conferida sem widget. Em painel estreito a
    conta dá negativa e vale o mínimo -- a linha então é mais curta que a
    medida, que é o comportamento desejado.
    """
    coluna = MEDIDA * largura_do_char
    return max(MARGEM_MINIMA, (largura - coluna) // 2)
