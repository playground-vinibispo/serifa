r"""A aparência: esquema de cores, fonte e medida da coluna de texto.

A decisão que organiza tudo aqui é que **isto não é um editor de código**. É um
instrumento para escrever uma página de prosa argumentada, e a marcação LaTeX é
andaime, não conteúdo. Daí o realce ser invertido em relação ao costume: num
editor de código o comando grita e o texto fica cinza; aqui a prosa recebe
tinta cheia e ``\section*``, ``\textbf`` e as chaves recuam para um cinza
quente. O que você lê e julga é o texto.

Pela mesma razão saíram os números de linha, a régua de 80 colunas e o realce
da linha atual: servem a código, não a um parágrafo de cem palavras.

Duas superfícies de papel, lado a lado: a folha de trabalho e a prova impressa.
O quadro em volta segue o tema do sistema -- escuro, aqui --, e é ele que faz
as duas folhas lerem como folhas.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")

from gi.repository import Gdk, GLib, Gtk, GtkSource

PAPEL = "#FAF8F3"
TINTA = "#23211D"
MARCACAO = "#A79E90"
ESTRUTURA = "#6B6255"
SEGUNDA_PENA = "#3E5C50"
ERRO = "#A33B2A"
SELECAO = "#E3DED2"
LINHA_ATUAL = "#F3EFE6"

FONTE = "JetBrainsMono NF"
CORPO = 11.5
MEDIDA = 74          # caracteres por linha; acima disso a leitura cansa
ENTRELINHA = 6       # pixels somados acima e abaixo de cada linha

ESQUEMA = f"""<?xml version="1.0" encoding="UTF-8"?>
<style-scheme id="serifa-papel" name="Serifa Papel" version="1.0">
  <author>Serifa</author>
  <description>Prosa em tinta cheia, marcação LaTeX recuada.</description>

  <color name="papel"        value="{PAPEL}"/>
  <color name="tinta"        value="{TINTA}"/>
  <color name="marcacao"     value="{MARCACAO}"/>
  <color name="estrutura"    value="{ESTRUTURA}"/>
  <color name="segundapena"  value="{SEGUNDA_PENA}"/>
  <color name="erro"         value="{ERRO}"/>
  <color name="selecao"      value="{SELECAO}"/>
  <color name="linhaatual"   value="{LINHA_ATUAL}"/>

  <style name="text"                background="papel" foreground="tinta"/>
  <style name="selection"           background="selecao" foreground="tinta"/>
  <style name="selection-unfocused" background="selecao"/>
  <style name="cursor"              foreground="erro"/>
  <style name="current-line"        background="linhaatual"/>
  <style name="bracket-match"       foreground="erro" bold="true"/>
  <style name="bracket-mismatch"    foreground="erro" background="selecao" bold="true"/>
  <style name="search-match"        background="#E7DCA8" foreground="tinta"/>

  <!-- A marcação recua. É andaime: precisa estar visível, não precisa brigar. -->
  <style name="latex:command"          foreground="marcacao"/>
  <style name="latex:common-commands"  foreground="marcacao"/>
  <style name="latex:special-char"     foreground="marcacao"/>
  <style name="latex:verbatim"         foreground="marcacao"/>

  <!-- A estrutura é o esqueleto do argumento: recuada, mas legível. -->
  <style name="latex:part"           foreground="estrutura" bold="true"/>
  <style name="latex:chapter"        foreground="estrutura" bold="true"/>
  <style name="latex:section"        foreground="estrutura" bold="true"/>
  <style name="latex:subsection"     foreground="estrutura" bold="true"/>
  <style name="latex:subsubsection"  foreground="estrutura"/>
  <style name="latex:paragraph"      foreground="estrutura"/>
  <style name="latex:subparagraph"   foreground="estrutura"/>
  <style name="latex:include"        foreground="estrutura"/>

  <!-- Matemática é a segunda pena: outra cor porque é outra linguagem. -->
  <style name="latex:display-math"   foreground="segundapena"/>
  <style name="latex:inline-math"    foreground="segundapena"/>
  <style name="latex:math"           foreground="segundapena"/>
  <style name="latex:math-boundary"  foreground="segundapena"/>

  <!-- Comentário some quase de todo: são lembretes meus, não o texto. -->
  <style name="latex:comment"  foreground="marcacao" italic="true"/>
  <style name="def:comment"    foreground="marcacao" italic="true"/>
  <style name="def:note"       foreground="estrutura" bold="true"/>

  <!-- Único vermelho do esquema. Se apareceu, é erro. -->
  <style name="def:error"      foreground="erro" underline="error" underline-color="erro"/>
</style-scheme>
"""

CSS = f"""
textview.serifa-editor {{
    font-family: "{FONTE}", "Red Hat Mono", monospace;
    font-size: {CORPO}pt;
    background-color: {PAPEL};
    color: {TINTA};
}}
textview.serifa-editor text {{
    background-color: {PAPEL};
}}
/* A prova: papel sobre a mesa escura, com fio em vez de sombra pesada. */
.serifa-prova {{
    background-color: shade(@window_bg_color, 0.82);
}}
.serifa-estado {{
    font-size: 0.85em;
}}
"""


def instalar_esquema() -> GtkSource.StyleScheme | None:
    """Grava o esquema no cache e o devolve carregado.

    Gerado em tempo de execução pelo mesmo motivo dos snippets: as cores ficam
    definidas uma vez, em Python, e não há XML para esquecer de atualizar.
    """
    pasta = Path(GLib.get_user_cache_dir()) / "serifa" / "styles"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "serifa-papel.xml").write_text(ESQUEMA, encoding="utf-8")

    gerente = GtkSource.StyleSchemeManager.get_default()
    caminhos = list(gerente.get_search_path() or [])
    if str(pasta) not in caminhos:
        gerente.set_search_path([str(pasta), *caminhos])
    gerente.force_rescan()
    return gerente.get_scheme("serifa-papel")


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
