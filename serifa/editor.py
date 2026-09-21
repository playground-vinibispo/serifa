"""O editor propriamente dito.

Um GtkSource.View configurado para LaTeX. O que há de menos óbvio aqui:

- o modo vim é o GtkSourceVimIMContext, que é a mesma emulação que o GNOME
  Builder usa -- escrita em C, não reimplementada em Python. Ligar e desligar é
  só adicionar ou remover um EventController;
- os pares automáticos vivem no sinal ``insert-text`` do buffer, e não num
  controlador de teclado. Isso é o que os faz conviver com o vim: em modo
  normal, teclar ``{`` é um movimento e não insere texto, então o sinal
  simplesmente não dispara.
"""

from __future__ import annotations

import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, GObject, Gtk, GtkSource

from .appearance import LEADING, character_width, margin_for
from .blocks import target

try:
    gi.require_version("Spelling", "1")
    from gi.repository import Spelling
except (ValueError, ImportError):  # pragma: no cover - depende do sistema
    Spelling = None

FECHAMENTO = {"{": "}", "[": "]", "(": ")", "$": "$"}
# Digitar o fechamento que já está sob o cursor deve passar por cima dele, não
# inserir um segundo. Sem isto, quem digita "\begin{align}" inteiro -- o que é
# o natural -- termina com "}}".
PASSAVEIS = {"}", "]", ")", "$"}

# Teclas que não são "uma tecla" para efeito de sequência: chegam sozinhas no
# meio de qualquer combinação. O caso que interessa é o Shift, sem o qual não
# se digita "{" -- ele aparece entre o "i" e o "{" de um vi{.
MODIFICADORES = {
    Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
    Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
    Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_Caps_Lock, Gdk.KEY_Shift_Lock,
    Gdk.KEY_Num_Lock, Gdk.KEY_Mode_switch,
    Gdk.KEY_ISO_Level3_Shift, Gdk.KEY_ISO_Level5_Shift,
}

# \begin{ambiente} seguido só de espaço até o fim da linha.
ABERTURA_DE_AMBIENTE = re.compile(r"\\begin\{([A-Za-z@*]+)\}[^\n]*$")


class Editor(GtkSource.View):
    """A área de texto, com o buffer e os comportamentos de edição."""

    __gtype_name__ = "SerifaEditor"

    __gsignals__ = {
        # Emitido quando o cursor muda de posição, para a barra de estado.
        "cursor-movido": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
    }

    def __init__(self) -> None:
        super().__init__()

        self.buffer = GtkSource.Buffer()
        self.set_buffer(self.buffer)

        idioma = GtkSource.LanguageManager.get_default().get_language("latex")
        if idioma is not None:
            self.buffer.set_language(idioma)
        self.buffer.set_highlight_matching_brackets(True)

        # Nada de número de linha, régua de 80 colunas ou realce da linha
        # atual: são instrumentos de código. Ver serifa/aparencia.py.
        self.set_show_line_numbers(False)
        self.set_highlight_current_line(False)
        self.set_show_right_margin(False)
        self.set_auto_indent(True)
        self.set_indent_on_tab(True)
        self.set_insert_spaces_instead_of_tabs(True)
        self.set_tab_width(2)
        self.set_indent_width(2)
        self.set_smart_backspace(True)
        self.set_smart_home_end(GtkSource.SmartHomeEndType.BEFORE)
        self.set_wrap_mode(Gtk.WrapMode.WORD)
        self.set_top_margin(28)
        self.set_bottom_margin(240)  # deixa a última linha subir até o meio da tela
        self.set_pixels_above_lines(LEADING // 2)
        self.set_pixels_below_lines(LEADING // 2)
        self.set_pixels_inside_wrap(LEADING // 2)
        self.add_css_class("serifa-editor")
        self._margem_atual = -1

        self._vim: GtkSource.VimIMContext | None = None
        self._controlador_vim: Gtk.EventControllerKey | None = None
        self._vinculo_foco = 0
        self._sequencia: list[str] = []   # teclas desde o último "v"
        self._tamanho_no_v = 0
        self._pares_automaticos = True
        self._inserindo = False  # trava de reentrância do insert-text

        # connect_after: no "depois" do insert-text o texto já entrou e o
        # iterador aponta logo após ele, o que dispensa adiar com idle_add.
        # Adiar era o bug: se o buffer fosse trocado nesse meio-tempo, a
        # marca guardada apontava para outro documento.
        self.buffer.connect("insert-text", self._antes_de_inserir)
        self.buffer.connect_after("insert-text", self._depois_de_inserir)
        self.buffer.connect("notify::cursor-position", self._ao_mover_cursor)

        self._adaptador_ortografico = None
        self._preparar_ortografia()

    def do_size_allocate(self, largura: int, altura: int, linha_base: int) -> None:
        """Centra a coluna de texto na largura disponível.

        No GTK4 não existe sinal de realocação para widget: "notify::width"
        não existe e conectar nele não faz nada. A forma é esta vfunc. A
        margem só é escrita quando muda, porque mexer em margem dispara nova
        alocação e reescrever o mesmo número a cada passagem é um laço.
        """
        if largura > 0:
            margem = margin_for(largura, character_width(self))
            if margem != self._margem_atual:
                self._margem_atual = margem
                self.set_left_margin(margem)
                self.set_right_margin(margem)
        GtkSource.View.do_size_allocate(self, largura, altura, linha_base)

    # ------------------------------------------------------------------ vim

    @property
    def vim_ativo(self) -> bool:
        return self._vim is not None

    def alternar_vim(self, ativo: bool) -> GtkSource.VimIMContext | None:
        """Liga ou desliga o modo vim. Devolve o contexto, quando ligado."""
        if ativo and self._vim is None:
            vim = GtkSource.VimIMContext()
            controlador = Gtk.EventControllerKey()
            controlador.set_im_context(vim)
            # CAPTURE: o vim precisa ver a tecla antes do GtkTextView.
            controlador.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.add_controller(controlador)
            vim.set_client_widget(self)

            # O GtkEventControllerKey só avisa focus_in ao contexto de entrada
            # quando o widget GANHA foco depois de o controlador existir. Ligar
            # o vim por Ctrl+Alt+V não troca o foco de lugar -- o editor já
            # estava focado --, então sem este empurrão o contexto nunca é
            # ativado e não filtra tecla nenhuma. E como o vim já pôs o
            # TextView em overwrite para desenhar o cursor em bloco do modo
            # normal, cada tecla que vaza não insere: sobrescreve. É o "modo
            # replace" que aparece do nada.
            if self.has_focus():
                vim.focus_in()

            self._vim = vim
            self._controlador_vim = controlador
            self._vinculo_foco = self.connect(
                "notify::has-focus", self._ao_mudar_foco
            )
        elif not ativo and self._vim is not None:
            self._vim.focus_out()
            self.disconnect(self._vinculo_foco)
            self._vinculo_foco = 0
            self._sequencia.clear()
            self.remove_controller(self._controlador_vim)
            self._vim = None
            self._controlador_vim = None
        return self._vim

    def _ao_mudar_foco(self, *_args) -> None:
        """Mantém o contexto do vim em dia com o foco, nos dois sentidos."""
        if self._vim is None:
            return
        if self.has_focus():
            self._vim.focus_in()
        else:
            self._vim.focus_out()

    # ------------------------------------------- text objects no modo visual

    def tratar_tecla(self, keyval: int, estado) -> bool:
        """Faz `vi{`, `va(`, `i"` e afins funcionarem no modo visual.

        O modo visual do GtkSourceView não tem text objects: a biblioteca traz
        gtk_source_vim_command_set_text_object e a versão para insert, mas o
        estado visual só expõe clone, get_bounds, ignore_command, new e warp.
        Daí `ci{` funcionar e `vi{` não -- ali o `i` é ignorado e o `{` vira o
        movimento "parágrafo anterior", que só pula o cursor.

        Aqui a sequência v -> i|a -> sinal é reconhecida e a seleção é feita à
        mão. O `v` segue para o vim, que entra em modo visual de verdade; o
        `i` e o sinal são consumidos, senão o vim os interpretaria como
        movimento.

        Chamado pelo controlador que a janela instala em si mesma, e não por um
        conectado ao controlador do vim. A diferença é decisiva: o
        GtkEventControllerKey entrega a tecla ao contexto de entrada ANTES de
        emitir key-pressed, e se o contexto filtrar -- que é o que o vim faz
        com tudo em modo normal -- o sinal nunca chega a ser emitido. Só
        modificadores soltos apareciam ali.
        """
        if self._vim is None:
            return False
        depurando = bool(os.environ.get("SERIFA_DEBUG"))

        if estado & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            self._sequencia.clear()
            return False

        if keyval in MODIFICADORES:
            # Não limpa a sequência: era exatamente isto que quebrava o vi{.
            # O "{" precisa de Shift, o Shift chega como tecla própria entre o
            # "i" e o "{", e a sequência morria aí -- o "{" chegava com a
            # máquina já zerada.
            return False

        codigo = Gdk.keyval_to_unicode(keyval)
        tecla = chr(codigo) if codigo else ""
        if depurando:
            print(
                f"[tecla] {tecla!r:5} keyval={keyval} sequência={self._sequencia} "
                f"seleção={bool(self.buffer.get_selection_bounds())}",
                flush=True,
            )
        if not tecla:
            self._sequencia.clear()
            return False

        if not self._sequencia:
            # Sem exigir ausência de seleção: em modo normal o vim pode manter
            # uma, e exigir que não houvesse era o que impedia a sequência de
            # armar -- o "v" entrava e saía sem deixar rastro.
            if tecla == "v":
                self._sequencia.append("v")
                self._tamanho_no_v = self.buffer.get_char_count()
            return False

        # Se o texto mudou desde o "v", estávamos em modo de inserção e aquele
        # "v" era só a letra v. Nada a fazer aqui.
        if self.buffer.get_char_count() != self._tamanho_no_v:
            if depurando:
                print("[tecla] texto mudou desde o v: era inserção, abortando",
                      flush=True)
            self._sequencia.clear()
            return False

        if len(self._sequencia) == 1:
            if tecla in ("i", "a"):
                self._sequencia.append(tecla)
                return True   # o vim não tem o que fazer com isto no visual
            self._sequencia.clear()
            return False

        por_dentro = self._sequencia[1] == "i"
        self._sequencia.clear()
        resultado = self._selecionar_bloco(tecla, por_dentro)
        if depurando and not resultado:
            print(f"[tecla] nenhum bloco {tecla!r} em volta do cursor", flush=True)
        return resultado

    def _selecionar_bloco(self, sinal: str, por_dentro: bool) -> bool:
        texto = self.texto
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        faixa = target(texto, cursor.get_offset(), sinal, por_dentro)
        if faixa is None:
            return False

        inicio, fim = faixa
        self._aplicar_selecao(inicio, fim)
        # O vim está em modo visual de verdade -- deixamos o "v" passar -- e
        # pode reajustar a seleção depois de nós: a dele é inclusiva do
        # caractere sob o cursor, a do GTK é exclusiva no fim. Em vez de supor
        # o sentido do ajuste e errar por um caractere para algum lado, a
        # seleção é medida num idle e reposta se tiver mudado.
        GLib.idle_add(self._corrigir_selecao, inicio, fim, texto)
        return True

    def _aplicar_selecao(self, inicio: int, fim: int) -> None:
        # Cursor no fim e âncora no começo, que é como o vim deixa o visual.
        self.buffer.select_range(
            self.buffer.get_iter_at_offset(fim),
            self.buffer.get_iter_at_offset(inicio),
        )

    def _corrigir_selecao(self, inicio: int, fim: int, texto: str) -> bool:
        limites = self.buffer.get_selection_bounds()
        atual = (
            (limites[0].get_offset(), limites[1].get_offset()) if limites else None
        )
        if atual != (inicio, fim):
            if os.environ.get("SERIFA_DEBUG"):
                print(
                    f"[bloco] queria ({inicio},{fim})={texto[inicio:fim]!r}, "
                    f"o vim deixou {atual}; repondo",
                    flush=True,
                )
            self._aplicar_selecao(inicio, fim)
        elif os.environ.get("SERIFA_DEBUG"):
            print(f"[bloco] ({inicio},{fim})={texto[inicio:fim]!r} intacta", flush=True)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------- pares e ambientes

    def _antes_de_inserir(
        self, buffer: GtkSource.Buffer, posicao: Gtk.TextIter, texto: str, tamanho: int
    ) -> None:
        """Passa por cima do fechamento em vez de duplicá-lo."""
        if self._inserindo or not self._pares_automaticos:
            return
        if texto not in PASSAVEIS or posicao.is_end():
            return
        if posicao.get_char() != texto:
            return
        buffer.stop_emission_by_name("insert-text")
        seguinte = posicao.copy()
        seguinte.forward_char()
        buffer.place_cursor(seguinte)

    def _depois_de_inserir(
        self, buffer: GtkSource.Buffer, posicao: Gtk.TextIter, texto: str, tamanho: int
    ) -> None:
        if self._inserindo or not self._pares_automaticos:
            return
        if texto in FECHAMENTO:
            self._fechar_par(buffer, posicao, texto)
        elif texto == "\n":
            self._fechar_ambiente(buffer, posicao)

    def _fechar_par(
        self, buffer: GtkSource.Buffer, posicao: Gtk.TextIter, abertura: str
    ) -> None:
        # Não duplica o $ quando o seguinte já é um $: aí o usuário está
        # fechando a matemática inline, não abrindo outra.
        if abertura == "$" and not posicao.is_end() and posicao.get_char() == "$":
            return

        entre = posicao.get_offset()
        self._inserindo = True
        buffer.insert(posicao, FECHAMENTO[abertura])
        self._inserindo = False
        buffer.place_cursor(buffer.get_iter_at_offset(entre))

    def _fechar_ambiente(self, buffer: GtkSource.Buffer, posicao: Gtk.TextIter) -> None:
        if posicao.get_line() == 0:
            return
        inicio = buffer.get_iter_at_line(posicao.get_line() - 1)
        if isinstance(inicio, tuple):  # a assinatura mudou entre versões
            inicio = inicio[1]
        fim = inicio.copy()
        if not fim.ends_line():
            fim.forward_to_line_end()
        linha = inicio.get_text(fim)

        casamento = ABERTURA_DE_AMBIENTE.search(linha)
        if casamento is None:
            return

        ambiente = casamento.group(1)
        recuo = re.match(r"[ \t]*", linha).group(0)
        dentro = posicao.get_offset() + len(recuo) + 2

        self._inserindo = True
        buffer.insert(posicao, f"{recuo}  \n{recuo}\\end{{{ambiente}}}")
        self._inserindo = False
        buffer.place_cursor(buffer.get_iter_at_offset(dentro))

    # ------------------------------------------------------------- ortografia

    def _preparar_ortografia(self) -> None:
        if Spelling is None:
            return
        provedor = Spelling.Provider.get_default()
        idiomas = {lingua.get_code() for lingua in provedor.list_languages()}
        # Preferência: português do Brasil, de Portugal, e só então o padrão.
        escolhido = next(
            (c for c in ("pt_BR", "pt_PT", "pt") if c in idiomas), None
        )
        if escolhido is None:
            # Sem dicionário de português instalado não vale corrigir em inglês
            # um texto que é todo em português: fica desligado.
            return
        verificador = Spelling.Checker.new(provedor, escolhido)
        adaptador = Spelling.TextBufferAdapter.new(self.buffer, verificador)
        self.set_extra_menu(adaptador.get_menu_model())
        self.insert_action_group("spelling", adaptador)
        adaptador.set_enabled(True)
        self._adaptador_ortografico = adaptador

    @property
    def tem_ortografia(self) -> bool:
        return self._adaptador_ortografico is not None

    # ------------------------------------------------------------- utilidades

    def _ao_mover_cursor(self, *_args) -> None:
        onde = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        self.emit("cursor-movido", onde.get_line() + 1, onde.get_line_offset() + 1)

    def ir_para_linha(self, linha: int) -> None:
        """Põe o cursor no começo da linha (1-based) e rola até lá."""
        linha = max(0, linha - 1)
        onde = self.buffer.get_iter_at_line(linha)
        if isinstance(onde, tuple):  # a assinatura mudou entre versões
            onde = onde[1]
        self.buffer.place_cursor(onde)
        self.scroll_to_iter(onde, 0.25, True, 0.0, 0.35)
        self.grab_focus()

    @property
    def texto(self) -> str:
        inicio, fim = self.buffer.get_bounds()
        return self.buffer.get_text(inicio, fim, True)

    def contar_palavras(self) -> int:
        # Tira comandos, matemática e comentários antes de contar: o que
        # interessa é a prosa, que é o que o limite de página cobra.
        texto = re.sub(r"(?m)%.*$", "", self.texto)
        texto = re.sub(r"\$[^$]*\$", "", texto)
        texto = re.sub(r"\\[A-Za-z@]+\*?", " ", texto)
        texto = re.sub(r"[{}\[\]~\\]", " ", texto)
        return len([p for p in texto.split() if any(c.isalnum() for c in p)])
