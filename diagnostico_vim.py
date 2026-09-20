"""Bisect do modo vim: da receita oficial até a Serifa inteira.

Toda tecla que chegar à fase de bolha é tecla que o contexto do vim NÃO
filtrou. Em modo normal, nenhuma tecla imprimível deveria chegar lá.

Variantes, em ordem crescente de "quanto da Serifa está em volta":

  minimo   a receita oficial do GtkSourceView, nada mais
  popup    a receita + um controlador de captura inerte antes do vim,
           imitando o do popup de completação
  editor   a classe serifa.editor.Editor, com o vim ligado pelo método dela
  janela   a Serifa inteira, com o detector grudado no editor de verdade

Rode em ordem e pare na primeira que vazar: a camada que entrou ali é a
culpada.
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk, GtkSource

VARIANTE = sys.argv[1] if len(sys.argv) > 1 else "minimo"
TEXTO = "abcdef\nghijkl\nmnopqr\n"


def detector(vista, aviso):
    """Gruda na fase de bolha e relata toda tecla que escapou do vim."""
    vazamentos = []

    def vazou(_c, keyval, _code, _estado):
        nome = Gdk.keyval_name(keyval) or "?"
        if nome.startswith(("Shift", "Control", "Alt", "Super", "Meta", "ISO")):
            return False
        vazamentos.append(nome)
        aviso(f"overwrite={vista.get_overwrite()}   "
              f"VAZOU ({len(vazamentos)}): {' '.join(vazamentos[-12:])}")
        print(f"VAZOU: {nome}", flush=True)
        return False

    bolha = Gtk.EventControllerKey()
    bolha.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
    bolha.connect("key-pressed", vazou)
    vista.add_controller(bolha)


def montar_janela_completa(app):
    """Variante 'janela': a Serifa de verdade, com o detector grudado."""
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from serifa.window import Janela
    from gi.repository import Adw

    janela = Janela(application=app)
    janela.present()
    editor = janela._editor
    janela._botao_vim.set_active(True)
    editor.grab_focus()
    detector(editor, lambda t: print(t, flush=True))

    # Registra toda tecla no ponto exato em que ela chega ao controlador do
    # vim, antes do filtro. "consumida=True" quer dizer que alguém da Serifa
    # ficou com ela e o vim nunca a viu.
    controlador_vim = editor._controlador_vim

    def espiar(_c, keyval, _code, estado):
        nome = Gdk.keyval_name(keyval) or "?"
        if nome.startswith(("Shift", "Control", "Alt", "Super", "Meta", "ISO")):
            return False
        print(
            f"tecla {nome:<12} balão={'aberto' if janela._popup.visivel else 'fechado':<7} "
            f"seleção={bool(editor.buffer.get_selection_bounds())} "
            f"completacao_nativa={editor.get_completion().get_property('view') is not None}",
            flush=True,
        )
        return False

    controlador_vim.connect("key-pressed", espiar)

    print(f"variante=janela  vim={editor.vim_ativo}  "
          f"overwrite={editor.get_overwrite()}", flush=True)
    print("Ponha o cursor dentro de {...} e tente: viw, depois ci{, depois vi{",
          flush=True)
    print("Cada tecla que o vim recebe aparece abaixo.", flush=True)


def montar(app):
    if VARIANTE == "janela":
        return montar_janela_completa(app)

    if VARIANTE == "editor":
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
        from serifa.editor import Editor
        vista = Editor()
        buffer = vista.buffer
    else:
        vista = GtkSource.View()
        buffer = vista.get_buffer()
    buffer.set_text(TEXTO)
    vista.set_monospace(True)
    vista.set_show_line_numbers(True)

    relato = Gtk.Label(label="digite:  j  k  x  i")
    relato.add_css_class("monospace")
    relato.set_xalign(0.0)
    relato.set_wrap(True)

    if VARIANTE == "popup":
        # O controlador do popup da Serifa, exatamente como lá: mesma fase,
        # adicionado ANTES do vim, devolvendo False sempre.
        antes = Gtk.EventControllerKey()
        antes.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        antes.connect("key-pressed", lambda *_: False)
        vista.add_controller(antes)

    if VARIANTE == "editor":
        vista.alternar_vim(True)   # o caminho da Serifa, não a receita crua
    else:
        vim = GtkSource.VimIMContext()
        chaves = Gtk.EventControllerKey()
        chaves.set_im_context(vim)
        chaves.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        vista.add_controller(chaves)
        vim.set_client_widget(vista)

    detector(vista, relato.set_label)

    caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    caixa.set_margin_start(12); caixa.set_margin_end(12)
    caixa.set_margin_top(12); caixa.set_margin_bottom(12)
    titulo = Gtk.Label()
    titulo.set_markup(
        f"<b>variante: {VARIANTE}</b>  —  se o vim funciona, "
        "<tt>j</tt> e <tt>k</tt> andam e NÃO aparece VAZOU"
    )
    titulo.set_xalign(0.0)
    caixa.append(titulo)
    caixa.append(vista)
    caixa.append(relato)

    janela = Gtk.ApplicationWindow(application=app, title=f"diagnóstico vim — {VARIANTE}")
    janela.set_default_size(560, 380)
    janela.set_child(caixa)
    janela.present()
    vista.grab_focus()
    print(f"variante={VARIANTE}  overwrite após ligar o vim={vista.get_overwrite()}", flush=True)


app = Gtk.Application(application_id=f"br.ufmg.vinibispo.DiagVim.{VARIANTE}")
app.connect("activate", montar)
sys.exit(app.run([]))
