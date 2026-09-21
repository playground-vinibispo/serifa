r"""A janela: sumário, editor, preview, diagnósticos e barra de estado."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, GtkSource

from .build import Compilador, Diagnostico
from .complete import FonteDeChaves, preparar_snippets
from .contexto import Acervo, Popup
from .editor import Editor
from .preview import Preview

# O conteúdo entre chaves pode quebrar linha e conter um nível de chaves
# aninhadas (\section*{\normalsize 1 --- ...}), então nada de [^}]* aqui.
SECAO = re.compile(
    r"^[ \t]*\\(chapter|section|subsection|subsubsection|paragraph)\*?\s*"
    r"\{((?:[^{}]|\{[^{}]*\})*)\}",
    re.MULTILINE | re.DOTALL,
)
NIVEL = {"chapter": 0, "section": 0, "subsection": 1, "subsubsection": 2, "paragraph": 3}

ESTADO = Path(GLib.get_user_config_dir()) / "serifa" / "estado.json"


class Janela(Adw.ApplicationWindow):
    __gtype_name__ = "SerifaJanela"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.set_title("Serifa")
        self.set_default_size(1500, 940)

        self._arquivo: Path | None = None
        self._sujo = False
        self._temporizador_compilacao = 0
        self._temporizador_sumario = 0
        self._compilacao_continua = True
        self._diagnosticos: list[Diagnostico] = []
        self._vigia: Gio.FileMonitor | None = None

        self._compilador = Compilador()
        self._compilador.connect("comecou", self._ao_comecar_compilacao)
        self._compilador.connect("terminou", self._ao_terminar_compilacao)

        self._montar()
        self._instalar_acoes()
        self._restaurar_estado()
        self.connect("close-request", self._ao_pedir_fechamento)

        # Na fase de captura o GTK despacha da raiz até o alvo, então um
        # controlador aqui na janela roda antes do controlador do vim, que
        # está no editor. É o único lugar de onde dá para ver as teclas que o
        # contexto de entrada do vim filtraria.
        teclas = Gtk.EventControllerKey()
        teclas.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        teclas.connect("key-pressed", self._ao_teclar)
        self.add_controller(teclas)

    def _ao_teclar(self, _controlador, keyval: int, _codigo: int, estado) -> bool:
        if not self._editor.has_focus():
            return False
        if self._popup.tratar_tecla(keyval, estado):
            return True
        return self._editor.tratar_tecla(keyval, estado)

    # ---------------------------------------------------------------- UI

    def _montar(self) -> None:
        self._editor = Editor()
        self._editor.buffer.connect("changed", self._ao_mudar_texto)
        self._editor.connect("cursor-movido", self._ao_mover_cursor)

        # Comandos e ambientes vêm de um .snippets gerado em serifa/complete.py.
        gerente = GtkSource.SnippetManager.get_default()
        caminhos = list(gerente.get_search_path() or [])
        pasta_snippets = str(preparar_snippets())
        if pasta_snippets not in caminhos:
            gerente.set_search_path([pasta_snippets, *caminhos])

        self._chaves = FonteDeChaves()
        completacao = self._editor.get_completion()
        completacao.add_provider(GtkSource.CompletionSnippets.new())

        palavras = GtkSource.CompletionWords.new("Documento")
        palavras.register(self._editor.buffer)
        completacao.add_provider(palavras)

        # Chaves de .bib e \label num buffer à parte: é assim que o
        # CompletionWords enxerga palavras que não estão no texto aberto.
        citacoes = GtkSource.CompletionWords.new("Citações e rótulos")
        citacoes.register(self._chaves.buffer)
        completacao.add_provider(citacoes)

        completacao.set_property("select-on-show", True)

        # Dentro de \cite{, \ref{, \begin{ e \input{ quem responde é um
        # popup próprio: ver o cabeçalho de serifa/contexto.py para o motivo.
        self._acervo = Acervo()
        self._popup = Popup(self._editor, self._acervo)

        rolagem = Gtk.ScrolledWindow()
        rolagem.set_child(self._editor)
        rolagem.set_vexpand(True)

        # --- busca e substituição
        self._busca = GtkSource.SearchContext.new(self._editor.buffer, None)
        self._busca.get_settings().set_wrap_around(True)
        self._campo_busca = Gtk.SearchEntry()
        self._campo_busca.set_placeholder_text("Buscar no texto")
        self._campo_busca.connect("search-changed", self._ao_buscar)
        self._campo_busca.connect("activate", lambda *_: self._proxima_ocorrencia())
        barra_busca = Gtk.SearchBar()
        barra_busca.set_child(self._campo_busca)
        barra_busca.connect_entry(self._campo_busca)
        self._barra_busca = barra_busca

        # --- diagnósticos
        self._lista_diagnosticos = Gtk.ListBox()
        self._lista_diagnosticos.add_css_class("boxed-list")
        self._lista_diagnosticos.connect("row-activated", self._ao_clicar_diagnostico)
        rolagem_diag = Gtk.ScrolledWindow()
        rolagem_diag.set_child(self._lista_diagnosticos)
        rolagem_diag.set_min_content_height(150)
        rolagem_diag.set_max_content_height(260)
        rolagem_diag.set_propagate_natural_height(True)
        self._painel_diagnosticos = Gtk.Revealer()
        self._painel_diagnosticos.set_child(rolagem_diag)
        self._painel_diagnosticos.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_UP
        )

        coluna_editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        coluna_editor.append(barra_busca)
        coluna_editor.append(rolagem)
        coluna_editor.append(self._painel_diagnosticos)

        # --- sumário
        self._sumario = Gtk.ListBox()
        self._sumario.add_css_class("navigation-sidebar")
        self._sumario.connect("row-activated", self._ao_clicar_sumario)
        rolagem_sumario = Gtk.ScrolledWindow()
        rolagem_sumario.set_child(self._sumario)
        rolagem_sumario.set_vexpand(True)
        caixa_sumario = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cabecalho_sumario = Adw.HeaderBar()
        cabecalho_sumario.set_show_end_title_buttons(False)
        cabecalho_sumario.set_title_widget(Adw.WindowTitle(title="Sumário"))
        caixa_sumario.append(cabecalho_sumario)
        caixa_sumario.append(rolagem_sumario)

        self._divisor_lateral = Adw.OverlaySplitView()
        self._divisor_lateral.set_sidebar(caixa_sumario)
        self._divisor_lateral.set_content(coluna_editor)
        self._divisor_lateral.set_max_sidebar_width(280)
        self._divisor_lateral.set_show_sidebar(True)

        # --- preview
        self._preview = Preview()
        self._divisor = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._divisor.set_start_child(self._divisor_lateral)
        self._divisor.set_end_child(self._preview)
        self._divisor.set_resize_start_child(True)
        self._divisor.set_resize_end_child(True)
        self._divisor.set_position(760)

        # --- cabeçalho
        cabecalho = Adw.HeaderBar()

        botao_abrir = Gtk.Button(icon_name="document-open-symbolic")
        botao_abrir.set_tooltip_text("Abrir (Ctrl+O)")
        botao_abrir.connect("clicked", lambda *_: self.abrir_dialogo())
        cabecalho.pack_start(botao_abrir)

        # Texto em vez de ícone: o document-save-symbolic do Adwaita atual é
        # uma seta caindo numa bandeja, indistinguível de "baixar". E o botão
        # só fica ativo havendo o que gravar, o que responde de relance a
        # pergunta "já salvei?".
        self._botao_salvar = Gtk.Button(label="Salvar")
        self._botao_salvar.set_tooltip_text("Salvar e compilar (Ctrl+S)")
        self._botao_salvar.set_sensitive(False)
        self._botao_salvar.connect("clicked", lambda *_: self.salvar())
        cabecalho.pack_start(self._botao_salvar)

        botao_sumario = Gtk.ToggleButton(icon_name="view-list-symbolic")
        botao_sumario.set_tooltip_text("Sumário (F9)")
        botao_sumario.set_active(True)
        botao_sumario.connect(
            "toggled", lambda b: self._divisor_lateral.set_show_sidebar(b.get_active())
        )
        cabecalho.pack_start(botao_sumario)

        formatacao = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        formatacao.add_css_class("linked")
        for nome, _comando, icone, rotulo in self.FORMATOS:
            if icone is None:
                continue
            botao_formato = Gtk.Button(icon_name=icone)
            dica = self.ATALHOS_DE_FORMATACAO.get(nome, "")
            botao_formato.set_tooltip_text(
                f"{rotulo} ({dica.replace('<Control>', 'Ctrl+')})" if dica else rotulo
            )
            botao_formato.set_action_name(f"win.{nome}")
            formatacao.append(botao_formato)
        cabecalho.pack_start(formatacao)

        self._titulo = Adw.WindowTitle(title="Serifa", subtitle="nenhum arquivo")
        cabecalho.set_title_widget(self._titulo)

        menu = Gio.Menu()
        secao_arquivo = Gio.Menu()
        secao_arquivo.append("Abrir…", "win.abrir")
        secao_arquivo.append("Salvar como…", "win.salvar-como")
        menu.append_section(None, secao_arquivo)
        secao_ver = Gio.Menu()
        secao_ver.append("Compilação contínua", "win.continua")
        secao_ver.append("Preview", "win.preview")
        secao_ver.append("Conferir texto", "win.conferir")
        menu.append_section(None, secao_ver)
        secao_formato = Gio.Menu()
        for nome, _comando, _icone, rotulo in self.FORMATOS:
            secao_formato.append(rotulo, f"win.{nome}")
        menu.append_submenu("Formatar", secao_formato)
        secao_zoom = Gio.Menu()
        secao_zoom.append("Ampliar PDF", "win.zoom-mais")
        secao_zoom.append("Reduzir PDF", "win.zoom-menos")
        secao_zoom.append("Ajustar à largura", "win.zoom-largura")
        menu.append_section(None, secao_zoom)
        botao_menu = Gtk.MenuButton(icon_name="open-menu-symbolic")
        botao_menu.set_menu_model(menu)
        cabecalho.pack_end(botao_menu)

        self._botao_vim = Gtk.ToggleButton(label="VIM")
        self._botao_vim.set_tooltip_text("Modo vim (Ctrl+Alt+V)")
        self._botao_vim.add_css_class("flat")
        self._botao_vim.connect("toggled", self._ao_alternar_vim)
        cabecalho.pack_end(self._botao_vim)

        self._botao_compilar = Gtk.Button(icon_name="media-playback-start-symbolic")
        self._botao_compilar.set_tooltip_text("Compilar (Ctrl+B)")
        self._botao_compilar.add_css_class("suggested-action")
        self._botao_compilar.connect("clicked", lambda *_: self.compilar())
        cabecalho.pack_end(self._botao_compilar)

        botao_busca = Gtk.ToggleButton(icon_name="edit-find-symbolic")
        botao_busca.set_tooltip_text("Buscar (Ctrl+F)")
        botao_busca.bind_property(
            "active", barra_busca, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL,
        )
        cabecalho.pack_end(botao_busca)

        # --- barra de estado
        self._estado_posicao = Gtk.Label(label="1:1")
        self._estado_palavras = Gtk.Label(label="0 palavras")
        self._estado_vim = Gtk.Label()
        self._estado_vim.add_css_class("monospace")
        self._estado_vim.set_xalign(0.0)
        self._estado_comando = Gtk.Label()
        self._estado_comando.add_css_class("monospace")
        self._estado_comando.set_hexpand(True)
        self._estado_comando.set_xalign(0.0)
        self._estado_compilacao = Gtk.Label(label="pronto")
        self._estado_compilacao.add_css_class("dim-label")

        barra_estado = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        barra_estado.set_margin_start(12)
        barra_estado.set_margin_end(12)
        barra_estado.set_margin_top(4)
        barra_estado.set_margin_bottom(4)
        for rotulo in (self._estado_posicao, self._estado_palavras,
                       self._estado_vim, self._estado_comando):
            rotulo.add_css_class("dim-label")
            barra_estado.append(rotulo)
        barra_estado.append(self._estado_compilacao)

        self._aviso = Adw.Banner()
        self._aviso.set_button_label("Recarregar")
        self._aviso.connect("button-clicked", lambda *_: self._recarregar())
        self._aviso.set_revealed(False)

        vista = Adw.ToolbarView()
        vista.add_top_bar(cabecalho)
        vista.add_top_bar(self._aviso)
        vista.set_content(self._divisor)
        vista.add_bottom_bar(barra_estado)

        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(vista)
        self.set_content(self._toasts)

    # ------------------------------------------------------------- ações

    def _instalar_acoes(self) -> None:
        atalhos = {
            "abrir": (self.abrir_dialogo, "<Control>o"),
            "salvar": (self.salvar, "<Control>s"),
            "salvar-como": (self.salvar_como, "<Control><Shift>s"),
            # Ctrl+B saiu de compilar e foi para negrito, que é onde o
            # mundo inteiro espera achá-lo.
            "compilar": (self.compilar, "F5"),
            "compilar-enter": (self.compilar, "<Control>Return"),
            "buscar": (self._focar_busca, "<Control>f"),
            "vim": (lambda: self._botao_vim.set_active(not self._botao_vim.get_active()), "<Control><Alt>v"),
            "preview": (self._alternar_preview, "<Control><Shift>v"),
            "sumario": (self._alternar_sumario, "F9"),
            "zoom-mais": (lambda: self._preview.aplicar_zoom(1.15), "<Control>plus"),
            "zoom-menos": (lambda: self._preview.aplicar_zoom(0.87), "<Control>minus"),
            "zoom-largura": (self._preview.ajustar_a_largura, "<Control>0"),
            "conferir": (self.conferir, "<Control><Shift>c"),
            "continua": (self._alternar_continua, None),
        }
        for nome, comando, _icone, _rotulo in self.FORMATOS:
            atalhos[nome] = (lambda c=comando: self.formatar(c), None)

        app = None
        for nome, (funcao, atalho) in atalhos.items():
            acao = Gio.SimpleAction.new(nome, None)
            acao.connect("activate", lambda _a, _p, f=funcao: f())
            self.add_action(acao)
            if atalho:
                app = app or self.get_application()
                if app is not None:
                    app.set_accels_for_action(f"win.{nome}", [atalho])

        self._aplicar_atalhos_de_formatacao(ligados=True)

    # ------------------------------------------------------- arquivo

    def abrir_dialogo(self) -> None:
        dialogo = Gtk.FileDialog()
        dialogo.set_title("Abrir um .tex")
        filtro = Gtk.FileFilter()
        filtro.set_name("LaTeX")
        filtro.add_pattern("*.tex")
        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)
        dialogo.set_filters(filtros)
        if self._arquivo:
            dialogo.set_initial_folder(Gio.File.new_for_path(str(self._arquivo.parent)))
        dialogo.open(self, None, self._ao_escolher_arquivo)

    def _ao_escolher_arquivo(self, dialogo, resultado) -> None:
        try:
            arquivo = dialogo.open_finish(resultado)
        except GLib.Error:
            return
        if arquivo is not None:
            self.abrir(Path(arquivo.get_path()))

    def abrir(self, caminho: Path) -> None:
        try:
            texto = caminho.read_text(encoding="utf-8")
        except OSError as erro:
            self._avisar(f"Não deu para abrir: {erro}")
            return

        self._editor.buffer.begin_irreversible_action()
        self._editor.buffer.set_text(texto)
        self._editor.buffer.end_irreversible_action()
        self._editor.buffer.set_modified(False)
        self._editor.buffer.place_cursor(self._editor.buffer.get_start_iter())

        self._arquivo = caminho
        self._sujo = False
        self._popup.reiniciar()
        self._vigiar(caminho)
        self._chaves.definir_pasta(caminho.parent)
        self._acervo.definir_pasta(caminho.parent)
        self._chaves.atualizar(texto)
        self._atualizar_titulo()
        self._reconstruir_sumario()
        self._atualizar_contagem()

        pdf = Compilador._pdf_de(caminho, caminho.parent)
        if pdf.exists():
            self._preview.carregar(pdf)
        # O Gtk.FileDialog é modal e leva o foco embora; sem devolvê-lo aqui,
        # as teclas seguintes podem não chegar ao contexto do vim.
        self._editor.grab_focus()
        self._guardar_estado()

    def salvar(self) -> bool:
        if self._arquivo is None:
            self.salvar_como()
            return False
        if not self._gravar():
            return False
        self._compilador.compilar(self._arquivo)
        return True

    def salvar_como(self) -> None:
        dialogo = Gtk.FileDialog()
        dialogo.set_title("Salvar como")
        if self._arquivo:
            dialogo.set_initial_name(self._arquivo.name)
        dialogo.save(self, None, self._ao_escolher_destino)

    def _ao_escolher_destino(self, dialogo, resultado) -> None:
        try:
            arquivo = dialogo.save_finish(resultado)
        except GLib.Error:
            return
        if arquivo is not None:
            self._arquivo = Path(arquivo.get_path())
            self._chaves.definir_pasta(self._arquivo.parent)
            self._acervo.definir_pasta(self._arquivo.parent)
            self.salvar()

    # ------------------------------------------------- arquivo mexido fora

    def _vigiar(self, caminho: Path) -> None:
        """Observa o arquivo aberto, para o editor não competir com o disco."""
        if self._vigia is not None:
            self._vigia.cancel()
        self._vigia = Gio.File.new_for_path(str(caminho)).monitor_file(
            Gio.FileMonitorFlags.NONE, None
        )
        self._vigia.connect("changed", self._ao_mudar_no_disco)

    def _ao_mudar_no_disco(self, _monitor, _arquivo, _outro, evento) -> None:
        if evento not in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
        ):
            return
        if self._arquivo is None:
            return
        try:
            em_disco = self._arquivo.read_text(encoding="utf-8")
        except OSError:
            return

        # Nossa própria gravação dispara o vigia: se o disco já é o que está
        # na tela, não há nada a fazer.
        if em_disco == self._editor.texto:
            self._aviso.set_revealed(False)
            return

        if self._sujo:
            # Com alteração não gravada, recarregar sozinho apagaria o
            # trabalho de alguém -- quem decide é o usuário.
            self._aviso.set_title(
                f"{self._arquivo.name} mudou no disco, e há alterações não salvas aqui"
            )
            self._aviso.set_revealed(True)
        else:
            self._recarregar()
            self._avisar(f"{self._arquivo.name} recarregado do disco")

    def _recarregar(self) -> None:
        """Relê o arquivo preservando onde o cursor estava."""
        if self._arquivo is None:
            return
        try:
            texto = self._arquivo.read_text(encoding="utf-8")
        except OSError as erro:
            self._avisar(f"Não deu para recarregar: {erro}")
            return

        buffer = self._editor.buffer
        onde = buffer.get_iter_at_mark(buffer.get_insert()).get_offset()
        buffer.begin_irreversible_action()
        buffer.set_text(texto)
        buffer.end_irreversible_action()
        buffer.set_modified(False)
        self._sujo = False
        self._aviso.set_revealed(False)
        buffer.place_cursor(
            buffer.get_iter_at_offset(min(onde, buffer.get_char_count()))
        )
        self._editor.scroll_to_mark(buffer.get_insert(), 0.25, True, 0.0, 0.35)
        self._atualizar_titulo()
        self._reconstruir_sumario()

    # ----------------------------------------------------- compilação

    def compilar(self) -> None:
        """Ctrl+B: grava e compila o arquivo de verdade.

        Gravar aqui é decisão do usuário, não efeito colateral -- pedir para
        compilar é pedir para materializar o que está na tela.
        """
        if self._arquivo is None:
            self._avisar("Salve o arquivo antes de compilar")
            return
        if self._sujo and not self._gravar():
            return
        self._compilador.compilar(self._arquivo)

    def previsualizar(self) -> None:
        """A contínua: compila o buffer sem encostar no arquivo do usuário."""
        if self._arquivo is None:
            return
        self._compilador.compilar_previa(self._editor.texto, self._arquivo)

    def _gravar(self) -> bool:
        try:
            self._arquivo.write_text(self._editor.texto, encoding="utf-8")
        except OSError as erro:
            self._avisar(f"Não deu para salvar: {erro}")
            return False
        self._editor.buffer.set_modified(False)
        self._sujo = False
        self._atualizar_titulo()
        return True

    def _ao_comecar_compilacao(self, _compilador, previa: bool) -> None:
        self._estado_compilacao.set_label("prévia…" if previa else "compilando…")
        self._botao_compilar.set_sensitive(False)

    def _ao_terminar_compilacao(
        self, _compilador, sucesso: bool, pdf: str, diagnosticos, previa: bool
    ) -> None:
        self._botao_compilar.set_sensitive(True)
        self._diagnosticos = list(diagnosticos)

        if pdf:
            self._preview.carregar(pdf)

        erros = sum(1 for d in self._diagnosticos if d.severidade == "erro")
        avisos = len(self._diagnosticos) - erros
        if sucesso:
            paginas = self._preview.paginas
            plural = "s" if paginas != 1 else ""
            resumo = f"{'prévia' if previa else 'ok'} · {paginas} página{plural}"
            if avisos:
                resumo += f" · {avisos} aviso{'s' if avisos != 1 else ''}"
            self._estado_compilacao.set_label(resumo)
        else:
            self._estado_compilacao.set_label(
                f"{erros} erro{'s' if erros != 1 else ''}" if erros else "falhou"
            )

        self._preencher_diagnosticos()

    def _preencher_diagnosticos(self) -> None:
        while (linha := self._lista_diagnosticos.get_first_child()) is not None:
            self._lista_diagnosticos.remove(linha)

        for diagnostico in self._diagnosticos[:60]:
            linha = Adw.ActionRow(title=GLib.markup_escape_text(diagnostico.resumo))
            linha.add_prefix(Gtk.Image.new_from_icon_name(diagnostico.icone))
            linha.diagnostico = diagnostico
            if diagnostico.linha:
                linha.set_activatable(True)
            self._lista_diagnosticos.append(linha)

        self._painel_diagnosticos.set_reveal_child(bool(self._diagnosticos))

    def _ao_clicar_diagnostico(self, _lista, linha) -> None:
        diagnostico = getattr(linha, "diagnostico", None)
        if diagnostico and diagnostico.linha:
            self._editor.ir_para_linha(diagnostico.linha)

    # ------------------------------------------------------------ formatação

    # (ação, comando LaTeX, ícone, rótulo no menu)
    FORMATOS = [
        ("negrito", "textbf", "format-text-bold-symbolic", "Negrito"),
        ("italico", "textit", "format-text-italic-symbolic", "Itálico"),
        ("sublinhado", "underline", "format-text-underline-symbolic", "Sublinhado"),
        ("monoespaco", "texttt", None, "Monoespaçado"),
        ("enfase", "emph", None, "Ênfase"),
        ("citacao", "enquote", None, "Entre aspas"),
        ("nota", "footnote", None, "Nota de rodapé"),
    ]

    def formatar(self, comando: str) -> None:
        """Envolve a seleção em \\comando{...}, ou abre as chaves no cursor."""
        buffer = self._editor.buffer
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
        self._editor.grab_focus()

    # -------------------------------------------------------- conferidor

    def conferir(self) -> None:
        """Roda o scripts/conferir-texto.py do projeto, quando há um."""
        if self._arquivo is None:
            return
        pasta = self._arquivo.parent
        script = None
        for candidata in [pasta, *pasta.parents]:
            possivel = candidata / "scripts" / "conferir-texto.py"
            if possivel.is_file():
                script = possivel
                break
        if script is None:
            self._avisar("Este projeto não tem scripts/conferir-texto.py")
            return

        try:
            saida = subprocess.run(
                ["/usr/bin/python3.12", str(script), str(pasta)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(script.parent.parent),
            )
        except (OSError, subprocess.TimeoutExpired) as erro:
            self._avisar(f"O conferidor falhou: {erro}")
            return

        self._diagnosticos = [
            Diagnostico("erro" if "ERRO" in linha else "aviso", linha.strip())
            for linha in saida.stdout.splitlines()
            if linha.strip() and ("ERRO" in linha or "aviso" in linha)
        ] or [Diagnostico("aviso", "conferidor: nada a resolver")]
        self._preencher_diagnosticos()

    # ------------------------------------------------------------ sumário

    def _reconstruir_sumario(self) -> None:
        while (linha := self._sumario.get_first_child()) is not None:
            self._sumario.remove(linha)

        texto = self._editor.texto
        for casamento in SECAO.finditer(texto):
            comando, titulo = casamento.group(1), casamento.group(2)
            numero = texto.count("\n", 0, casamento.start()) + 1
            limpo = re.sub(r"\\[A-Za-z]+\*?|[{}]", "", titulo)
            rotulo = Gtk.Label(label=" ".join(limpo.split()))
            rotulo.set_xalign(0.0)
            rotulo.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            rotulo.set_margin_start(8 + 14 * NIVEL.get(comando, 0))
            rotulo.set_margin_end(8)
            rotulo.set_margin_top(4)
            rotulo.set_margin_bottom(4)
            if NIVEL.get(comando, 0) == 0:
                rotulo.add_css_class("heading")
            linha = Gtk.ListBoxRow()
            linha.set_child(rotulo)
            linha.numero_da_linha = numero
            self._sumario.append(linha)

    def _ao_clicar_sumario(self, _lista, linha) -> None:
        numero = getattr(linha, "numero_da_linha", None)
        if numero:
            self._editor.ir_para_linha(numero)

    # ------------------------------------------------------------- busca

    def _focar_busca(self) -> None:
        self._barra_busca.set_search_mode(True)
        self._campo_busca.grab_focus()

    def _ao_buscar(self, campo) -> None:
        self._busca.get_settings().set_search_text(campo.get_text() or None)

    def _proxima_ocorrencia(self) -> None:
        cursor = self._editor.buffer.get_iter_at_mark(self._editor.buffer.get_insert())
        cursor.forward_char()
        deu, inicio, fim, _ = self._busca.forward(cursor)
        if deu:
            self._editor.buffer.select_range(inicio, fim)
            self._editor.scroll_to_iter(inicio, 0.25, True, 0.0, 0.35)

    # ------------------------------------------------------------- estado

    def _ao_mudar_texto(self, _buffer) -> None:
        if not self._sujo:
            self._sujo = True
            self._atualizar_titulo()

        if self._temporizador_sumario:
            GLib.source_remove(self._temporizador_sumario)
        self._temporizador_sumario = GLib.timeout_add(
            600, self._tarefa_sumario
        )

        if self._compilacao_continua and self._arquivo is not None:
            if self._temporizador_compilacao:
                GLib.source_remove(self._temporizador_compilacao)
            self._temporizador_compilacao = GLib.timeout_add(
                1400, self._tarefa_compilacao
            )

    def _tarefa_sumario(self) -> bool:
        self._temporizador_sumario = 0
        self._reconstruir_sumario()
        self._atualizar_contagem()
        self._chaves.atualizar(self._editor.texto)
        return GLib.SOURCE_REMOVE

    def _tarefa_compilacao(self) -> bool:
        self._temporizador_compilacao = 0
        self.previsualizar()
        return GLib.SOURCE_REMOVE

    def _ao_mover_cursor(self, _editor, linha: int, coluna: int) -> None:
        self._estado_posicao.set_label(f"{linha}:{coluna}")

    def _atualizar_contagem(self) -> None:
        total = self._editor.contar_palavras()
        self._estado_palavras.set_label(f"{total} palavras")

    def _atualizar_titulo(self) -> None:
        self._botao_salvar.set_sensitive(self._sujo and self._arquivo is not None)
        if self._arquivo is None:
            self._titulo.set_title("Serifa")
            self._titulo.set_subtitle("nenhum arquivo")
            return
        marca = " •" if self._sujo else ""
        self._titulo.set_title(f"{self._arquivo.name}{marca}")
        self._titulo.set_subtitle(str(self._arquivo.parent).replace(str(Path.home()), "~"))

    # ------------------------------------------------------------- toggles

    def _ao_alternar_vim(self, botao: Gtk.ToggleButton) -> None:
        vim = self._editor.alternar_vim(botao.get_active())
        if vim is not None:
            # O VimIMContext não expõe o modo atual em lugar nenhum: só tem
            # command-bar-text (que traz "-- INSERT --", ":w", "/busca") e
            # command-text (o comando em digitação, como "2d"). Mostrar os dois
            # crus é o mais perto de um indicador de modo que dá para ter --
            # e é melhor que o "-- modo vim --" fixo que estava aqui, que não
            # dizia se você estava em normal ou em insert.
            vim.bind_property("command-bar-text", self._estado_vim, "label")
            vim.bind_property("command-text", self._estado_comando, "label")
            self._estado_vim.set_label("")
            self._aplicar_atalhos_de_formatacao(ligados=False)
            botao.add_css_class("accent")
        else:
            self._estado_vim.set_label("")
            self._estado_comando.set_label("")
            self._aplicar_atalhos_de_formatacao(ligados=True)
            botao.remove_css_class("accent")
        self._editor.grab_focus()
        self._guardar_estado()

    def _alternar_preview(self) -> None:
        visivel = self._preview.get_visible()
        self._preview.set_visible(not visivel)

    def _alternar_sumario(self) -> None:
        self._divisor_lateral.set_show_sidebar(
            not self._divisor_lateral.get_show_sidebar()
        )

    def _alternar_continua(self) -> None:
        self._compilacao_continua = not self._compilacao_continua
        self._avisar(
            "Compilação contínua ligada"
            if self._compilacao_continua
            else "Compilação contínua desligada"
        )
        self._guardar_estado()

    def _avisar(self, mensagem: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=mensagem, timeout=3))

    # os dois que o mundo espera; os demais ficam só no menu, para não
    # atropelar mais teclas do vim do que o necessário
    ATALHOS_DE_FORMATACAO = {"negrito": "<Control>b", "italico": "<Control>i"}

    def _aplicar_atalhos_de_formatacao(self, ligados: bool) -> None:
        """Com o vim ligado, Ctrl+B e Ctrl+I voltam a ser dele.

        Acelerador de janela é resolvido antes dos controladores do widget, ou
        seja, venceria o vim sem nem avisar. Quem usa vim espera Ctrl+B como
        página acima; os botões da barra continuam valendo de qualquer jeito.
        """
        app = self.get_application()
        if app is None:
            return
        for nome, atalho in self.ATALHOS_DE_FORMATACAO.items():
            app.set_accels_for_action(f"win.{nome}", [atalho] if ligados else [])

    # ------------------------------------------------------------ fechamento

    def _ao_pedir_fechamento(self, *_args) -> bool:
        """Bloqueia o fechamento enquanto houver alteração não gravada."""
        if not self._sujo or self._arquivo is None:
            return False  # deixa fechar

        dialogo = Adw.AlertDialog(
            heading="Salvar antes de sair?",
            body=f"As alterações em {self._arquivo.name} não foram gravadas.",
        )
        dialogo.add_response("cancelar", "Cancelar")
        dialogo.add_response("descartar", "Descartar")
        dialogo.add_response("salvar", "Salvar")
        dialogo.set_response_appearance("descartar", Adw.ResponseAppearance.DESTRUCTIVE)
        dialogo.set_response_appearance("salvar", Adw.ResponseAppearance.SUGGESTED)
        dialogo.set_default_response("salvar")
        dialogo.set_close_response("cancelar")
        dialogo.choose(self, None, self._ao_responder_fechamento)
        return True  # segura a janela até a resposta

    def _ao_responder_fechamento(self, dialogo, resultado) -> None:
        try:
            resposta = dialogo.choose_finish(resultado)
        except GLib.Error:
            return
        if resposta == "cancelar":
            return
        if resposta == "salvar" and not self._gravar():
            return
        self._sujo = False  # o close-request seguinte passa direto
        self.close()

    # -------------------------------------------------------- persistência

    def _guardar_estado(self) -> None:
        try:
            ESTADO.parent.mkdir(parents=True, exist_ok=True)
            ESTADO.write_text(
                json.dumps(
                    {
                        "arquivo": str(self._arquivo) if self._arquivo else None,
                        "vim": self._botao_vim.get_active(),
                        "continua": self._compilacao_continua,
                        "divisor": self._divisor.get_position(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _restaurar_estado(self) -> None:
        try:
            dados = json.loads(ESTADO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if dados.get("vim"):
            self._botao_vim.set_active(True)
        self._compilacao_continua = dados.get("continua", True)
        if posicao := dados.get("divisor"):
            self._divisor.set_position(posicao)
        if caminho := dados.get("arquivo"):
            if Path(caminho).exists():
                # Só restaura se nada tiver sido aberto nesse meio-tempo: a
                # linha de comando (do_open) chega antes deste idle, e sem a
                # guarda a sessão anterior sobrescrevia o arquivo pedido.
                def restaurar() -> bool:
                    if self._arquivo is None:
                        self.abrir(Path(caminho))
                    return GLib.SOURCE_REMOVE

                GLib.idle_add(restaurar)
