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

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GObject, Gtk, GtkSource

from .blocos import alvo

try:
    gi.require_version("Spelling", "1")
    from gi.repository import Spelling
except (ValueError, ImportError):  # pragma: no cover - depende do sistema
    Spelling = None

FECHAMENTO = {"{": "}", "[": "]", "(": ")", "$": "$"}

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

        self.set_monospace(True)
        self.set_show_line_numbers(True)
        self.set_highlight_current_line(True)
        self.set_auto_indent(True)
        self.set_indent_on_tab(True)
        self.set_insert_spaces_instead_of_tabs(True)
        self.set_tab_width(2)
        self.set_indent_width(2)
        self.set_smart_backspace(True)
        self.set_smart_home_end(GtkSource.SmartHomeEndType.BEFORE)
        self.set_show_right_margin(True)
        self.set_right_margin_position(80)
        self.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.set_left_margin(12)
        self.set_right_margin(12)
        self.set_top_margin(8)
        self.set_bottom_margin(240)  # deixa a última linha subir até o meio da tela
        self.set_pixels_above_lines(1)
        self.set_pixels_below_lines(1)

        self._vim: GtkSource.VimIMContext | None = None
        self._controlador_vim: Gtk.EventControllerKey | None = None
        self._vinculo_foco = 0
        self._vinculo_teclas = 0
        self._sequencia: list[str] = []   # teclas desde o último "v"
        self._tamanho_no_v = 0
        self._pares_automaticos = True
        self._inserindo = False  # trava de reentrância do insert-text

        # connect_after: no "depois" do insert-text o texto já entrou e o
        # iterador aponta logo após ele, o que dispensa adiar com idle_add.
        # Adiar era o bug: se o buffer fosse trocado nesse meio-tempo, a
        # marca guardada apontava para outro documento.
        self.buffer.connect_after("insert-text", self._depois_de_inserir)
        self.buffer.connect("notify::cursor-position", self._ao_mover_cursor)

        self._adaptador_ortografico = None
        self._preparar_ortografia()

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
            # Conectado ao sinal, este handler roda ANTES do tratador padrão
            # do controlador, que é quem chama o filtro do vim.
            self._vinculo_teclas = controlador.connect(
                "key-pressed", self._ao_teclar_no_vim
            )
        elif not ativo and self._vim is not None:
            self._vim.focus_out()
            self.disconnect(self._vinculo_foco)
            self._vinculo_foco = 0
            if self._vinculo_teclas:
                self._controlador_vim.disconnect(self._vinculo_teclas)
                self._vinculo_teclas = 0
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

    def _ao_teclar_no_vim(self, _controlador, keyval, _codigo, estado) -> bool:
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
        """
        if estado & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            self._sequencia.clear()
            return False

        codigo = Gdk.keyval_to_unicode(keyval)
        tecla = chr(codigo) if codigo else ""
        if not tecla:
            self._sequencia.clear()
            return False

        if not self._sequencia:
            if tecla == "v" and not self.buffer.get_selection_bounds():
                self._sequencia.append("v")
                self._tamanho_no_v = self.buffer.get_char_count()
            return False

        # Se o texto mudou desde o "v", estávamos em modo de inserção e aquele
        # "v" era só a letra v. Nada a fazer aqui.
        if self.buffer.get_char_count() != self._tamanho_no_v:
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
        return self._selecionar_bloco(tecla, por_dentro)

    def _selecionar_bloco(self, sinal: str, por_dentro: bool) -> bool:
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        faixa = alvo(self.texto, cursor.get_offset(), sinal, por_dentro)
        if faixa is None:
            return False
        inicio, fim = faixa
        # Cursor no fim e âncora no começo, como o vim deixa.
        self.buffer.select_range(
            self.buffer.get_iter_at_offset(fim),
            self.buffer.get_iter_at_offset(inicio),
        )
        return True

    # ------------------------------------------------------- pares e ambientes

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
