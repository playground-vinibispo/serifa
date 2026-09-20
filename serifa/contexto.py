"""Completação sensível ao contexto.

O GtkSourceView não pode ajudar aqui. Um GtkSourceCompletionProvider próprio
seria o caminho natural, mas o par ``populate_async``/``populate_finish`` não é
implementável em PyGObject: o callback em C do GtkSourceView recebe um
``result`` que não é a GTask e um ``user_data`` corrompido, e o processo morre
em ``gtk_source_completion_context_set_proposals_for_provider``. O backtrace
está no README. Não é erro de uso -- o binding não tem como repassar o
``user_data`` original de um ``GAsyncReadyCallback`` vindo de vfunc.

Então o popup destes quatro casos é widget próprio:

- ``\\cite{`` -> chaves dos .bib do projeto, com o título ao lado;
- ``\\ref{``  -> os ``\\label`` do documento aberto;
- ``\\begin{``/``\\end{`` -> ambientes;
- ``\\input{``/``\\includegraphics{`` -> arquivos da pasta.

A completação geral (comandos, ambientes como snippet, palavras do documento)
continua sendo a nativa do GtkSourceView. Esta aqui só aparece dentro das
chaves desses comandos, onde a nativa não teria o que oferecer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk

# O que vem imediatamente à esquerda do cursor decide a fonte. O grupo
# capturado é o que já foi digitado dentro das chaves.
CITACAO = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\])*\{([^}]*)$")
REFERENCIA = re.compile(r"\\(?:page|eq|auto|name|c)?ref\*?\{([^}]*)$")
AMBIENTE = re.compile(r"\\(?:begin|end)\{([^}]*)$")
# Separados porque pedem coisas diferentes: \input quer fonte,
# \includegraphics quer imagem. Oferecer os dois juntos é ruído.
ENTRADA = re.compile(r"\\(?:input|include|bibliography)(?:\[[^\]]*\])?\{([^}]*)$")
GRAFICO = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)$")

CHAVE_BIB = re.compile(r"@\w+\s*\{\s*([^,\s]+)", re.MULTILINE)
CAMPO_BIB = re.compile(r"(title|author)\s*=\s*[{\"](.+?)[}\"]\s*,", re.IGNORECASE | re.DOTALL)
ROTULO = re.compile(r"\\label\{([^}]+)\}")

AMBIENTES = [
    "document", "abstract", "itemize", "enumerate", "description",
    "figure", "table", "tabular", "center", "flushleft", "flushright",
    "quote", "quotation", "verse", "verbatim", "equation", "equation*",
    "align", "align*", "gather", "gather*", "matrix", "pmatrix", "bmatrix",
    "cases", "array", "minipage", "thebibliography",
]

EXTENSOES = {
    "entrada": {".tex", ".bib"},
    "grafico": {".png", ".jpg", ".jpeg", ".pdf", ".eps"},
}


@dataclass(frozen=True)
class Item:
    texto: str          # o que é inserido
    detalhe: str = ""   # o que aparece esmaecido ao lado
    icone: str = ""


@dataclass(frozen=True)
class Contexto:
    tipo: str           # "citacao"|"referencia"|"ambiente"|"entrada"|"grafico"|""
    prefixo: str        # o que já foi digitado dentro das chaves
    inicio: int         # offset onde o prefixo começa, para substituir


def detectar(texto_a_esquerda: str, offset_do_cursor: int) -> Contexto:
    """Decide o contexto a partir do texto à esquerda do cursor.

    Função pura de propósito: é o pedaço que dá para testar sem abrir janela.
    """
    for tipo, padrao in (
        ("citacao", CITACAO),
        ("referencia", REFERENCIA),
        ("ambiente", AMBIENTE),
        ("grafico", GRAFICO),   # antes de ENTRADA: \includegraphics casa os dois
        ("entrada", ENTRADA),
    ):
        casamento = padrao.search(texto_a_esquerda)
        if casamento is not None:
            prefixo = casamento.group(1)
            # Numa citação múltipla (\cite{a,b}), só o trecho depois da
            # última vírgula conta como prefixo.
            if tipo == "citacao" and "," in prefixo:
                prefixo = prefixo.rsplit(",", 1)[1].lstrip()
            return Contexto(tipo, prefixo, offset_do_cursor - len(prefixo))
    return Contexto("", "", offset_do_cursor)


class Acervo:
    """As fontes de dados: chaves de .bib, rótulos e arquivos da pasta."""

    def __init__(self) -> None:
        self._pasta: Path | None = None
        self._citacoes: list[Item] = []
        self._arquivos: dict[str, list[Item]] = {"entrada": [], "grafico": []}

    def definir_pasta(self, pasta: Path | None) -> None:
        if pasta == self._pasta:
            return
        self._pasta = pasta
        self._citacoes = self._ler_bibs(pasta) if pasta else []
        self._arquivos = {
            especie: self._listar_arquivos(pasta, especie) if pasta else []
            for especie in EXTENSOES
        }

    def itens(self, contexto: Contexto, texto_do_documento: str) -> list[Item]:
        if contexto.tipo == "citacao":
            candidatos = self._citacoes
        elif contexto.tipo == "referencia":
            candidatos = [
                Item(r, "label", "mark-location-symbolic")
                for r in sorted(set(ROTULO.findall(texto_do_documento)))
            ]
        elif contexto.tipo == "ambiente":
            candidatos = [
                Item(a, "ambiente", "view-list-symbolic") for a in AMBIENTES
            ]
        elif contexto.tipo in self._arquivos:
            candidatos = self._arquivos[contexto.tipo]
        else:
            return []

        alvo = contexto.prefixo.lower()
        if not alvo:
            return candidatos
        # Casamento por subsequência, como em editor de código: "eif" acha
        # "einstein_infeld".
        return [i for i in candidatos if _subsequencia(alvo, i.texto.lower())]

    # ------------------------------------------------------------- leitura

    @staticmethod
    def _ler_bibs(pasta: Path) -> list[Item]:
        itens: list[Item] = []
        vistas: set[str] = set()
        # A pasta do arquivo e até três níveis acima: cobre o layout
        # trabalho/ -> referencias.bib na raiz do repositório.
        for diretorio in [pasta, *list(pasta.parents)[:3]]:
            try:
                arquivos = sorted(diretorio.glob("*.bib"))
            except OSError:
                continue
            for arquivo in arquivos:
                try:
                    bruto = arquivo.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for bloco in re.split(r"(?=@\w+\s*\{)", bruto):
                    chave = CHAVE_BIB.search(bloco)
                    if not chave or chave.group(1) in vistas:
                        continue
                    vistas.add(chave.group(1))
                    campos = {c.lower(): v for c, v in CAMPO_BIB.findall(bloco)}
                    resumo = campos.get("title") or campos.get("author") or arquivo.name
                    itens.append(
                        Item(
                            chave.group(1),
                            " ".join(resumo.split())[:60],
                            "user-bookmarks-symbolic",
                        )
                    )
        return itens

    @staticmethod
    def _listar_arquivos(pasta: Path, especie: str) -> list[Item]:
        itens: list[Item] = []
        aceitas = EXTENSOES[especie]
        for base in (pasta, pasta.parent, pasta.parent.parent):
            try:
                entradas = sorted(base.iterdir())
            except OSError:
                continue
            for entrada in entradas:
                if not entrada.is_file() or entrada.suffix.lower() not in aceitas:
                    continue
                try:
                    relativo = entrada.relative_to(pasta)
                    nome = str(relativo)
                except ValueError:
                    # Sobe com ../ enquanto for razoável.
                    salto = len(pasta.relative_to(base).parts)
                    nome = "../" * salto + entrada.name
                # O \input dispensa a extensão .tex.
                if entrada.suffix == ".tex":
                    nome = nome[: -len(".tex")]
                if not any(i.texto == nome for i in itens):
                    icone = ("image-x-generic-symbolic" if especie == "grafico"
                             else "text-x-generic-symbolic")
                    itens.append(Item(nome, entrada.suffix.lstrip("."), icone))
        return itens[:60]


def _subsequencia(agulha: str, palheiro: str) -> bool:
    posicao = 0
    for caractere in agulha:
        posicao = palheiro.find(caractere, posicao) + 1
        if posicao == 0:
            return False
    return True


class Popup:
    """O balão de completação, ancorado no cursor.

    As teclas de navegação são capturadas num controlador próprio do editor.
    Enquanto o balão está aberto, o controlador do vim é posto em
    ``PropagationPhase.NONE``: sem isso o vim engoliria as setas e o Enter,
    porque ele também escuta na fase de captura.
    """

    def __init__(self, editor, acervo: Acervo) -> None:
        self._editor = editor
        self._acervo = acervo
        self._itens: list[Item] = []
        self._contexto = Contexto("", "", 0)
        self._temporizador = 0
        self._suprimir = False

        self._lista = Gtk.ListBox()
        self._lista.set_activate_on_single_click(True)
        self._lista.connect("row-activated", lambda _l, linha: self._aceitar(linha.get_index()))

        rolagem = Gtk.ScrolledWindow()
        rolagem.set_child(self._lista)
        rolagem.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        rolagem.set_max_content_height(260)
        rolagem.set_propagate_natural_height(True)
        rolagem.set_propagate_natural_width(True)

        self._balao = Gtk.Popover()
        self._balao.set_child(rolagem)
        self._balao.set_autohide(False)          # o foco continua no editor
        self._balao.set_position(Gtk.PositionType.BOTTOM)
        self._balao.set_has_arrow(False)
        self._balao.set_parent(editor)

        teclas = Gtk.EventControllerKey()
        teclas.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        teclas.connect("key-pressed", self._ao_teclar)
        editor.add_controller(teclas)

        editor.buffer.connect_after("changed", self._agendar)
        editor.buffer.connect("notify::cursor-position", self._agendar)

    # ------------------------------------------------------------- estado

    @property
    def visivel(self) -> bool:
        return self._balao.get_visible()

    def _agendar(self, *_args) -> None:
        if self._temporizador:
            GLib.source_remove(self._temporizador)
        self._temporizador = GLib.timeout_add(60, self._reavaliar)

    def _reavaliar(self) -> bool:
        self._temporizador = 0
        if self._suprimir:
            # A própria inserção que acabamos de fazer dispara uma
            # reavaliação; sem esta trava o popup reabriria sobre o que o
            # usuário acabou de escolher.
            self._suprimir = False
            return GLib.SOURCE_REMOVE
        buffer = self._editor.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        inicio = cursor.copy()
        inicio.set_line_offset(0)

        self._contexto = detectar(inicio.get_text(cursor), cursor.get_offset())
        if not self._contexto.tipo:
            self.fechar()
            return GLib.SOURCE_REMOVE

        self._itens = self._acervo.itens(self._contexto, self._editor.texto)
        if not self._itens:
            self.fechar()
            return GLib.SOURCE_REMOVE

        self._preencher()
        self._posicionar(cursor)
        self._balao.popup()
        # A nativa e esta não podem aparecer juntas.
        self._editor.get_completion().hide()
        self._silenciar_vim(True)
        return GLib.SOURCE_REMOVE

    def fechar(self) -> None:
        if self._balao.get_visible():
            self._balao.popdown()
            self._silenciar_vim(False)

    def _silenciar_vim(self, silenciar: bool) -> None:
        controlador = getattr(self._editor, "_controlador_vim", None)
        if controlador is None:
            return
        controlador.set_propagation_phase(
            Gtk.PropagationPhase.NONE if silenciar else Gtk.PropagationPhase.CAPTURE
        )

    # ---------------------------------------------------------------- UI

    def _preencher(self) -> None:
        while (linha := self._lista.get_first_child()) is not None:
            self._lista.remove(linha)

        for item in self._itens[:40]:
            caixa = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            caixa.set_margin_start(8); caixa.set_margin_end(8)
            caixa.set_margin_top(3); caixa.set_margin_bottom(3)
            if item.icone:
                caixa.append(Gtk.Image.new_from_icon_name(item.icone))
            nome = Gtk.Label(label=item.texto)
            nome.add_css_class("monospace")
            nome.set_xalign(0.0)
            caixa.append(nome)
            if item.detalhe:
                detalhe = Gtk.Label(label=item.detalhe)
                detalhe.add_css_class("dim-label")
                detalhe.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
                detalhe.set_xalign(0.0)
                detalhe.set_hexpand(True)
                caixa.append(detalhe)
            linha = Gtk.ListBoxRow()
            linha.set_child(caixa)
            self._lista.append(linha)

        primeira = self._lista.get_row_at_index(0)
        if primeira is not None:
            self._lista.select_row(primeira)

    def _posicionar(self, cursor) -> None:
        area = self._editor.get_iter_location(cursor)
        x, y = self._editor.buffer_to_window_coords(
            Gtk.TextWindowType.WIDGET, area.x, area.y + area.height
        )
        self._balao.set_pointing_to(Gdk.Rectangle(x=x, y=y, width=1, height=1))

    # ------------------------------------------------------------ teclado

    def _ao_teclar(self, _controlador, keyval: int, _keycode: int, estado) -> bool:
        if not self.visivel:
            return False

        selecionada = self._lista.get_selected_row()
        indice = selecionada.get_index() if selecionada else 0
        total = min(len(self._itens), 40)

        if keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self._selecionar((indice + 1) % total)
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_ISO_Left_Tab):
            self._selecionar((indice - 1) % total)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._aceitar(indice)
            return True
        if keyval == Gdk.KEY_Escape:
            self.fechar()
            return True
        return False

    def _selecionar(self, indice: int) -> None:
        linha = self._lista.get_row_at_index(indice)
        if linha is not None:
            self._lista.select_row(linha)
            linha.grab_focus()
            self._editor.grab_focus()  # o foco volta: quem digita é o editor

    def _aceitar(self, indice: int) -> None:
        if not (0 <= indice < len(self._itens)):
            return
        item = self._itens[indice]
        buffer = self._editor.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        inicio = buffer.get_iter_at_offset(self._contexto.inicio)

        self.fechar()
        self._suprimir = True
        buffer.begin_user_action()
        buffer.delete(inicio, cursor)
        buffer.insert(inicio, item.texto)
        buffer.end_user_action()

        # Pula o } que os pares automáticos deixaram à frente: é para lá que
        # o cursor iria de qualquer jeito.
        depois = buffer.get_iter_at_mark(buffer.get_insert())
        if not depois.is_end() and depois.get_char() == "}":
            depois.forward_char()
            buffer.place_cursor(depois)

        self._editor.grab_focus()
