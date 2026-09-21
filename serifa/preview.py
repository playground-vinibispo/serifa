"""O painel do PDF.

Renderiza com Poppler direto em cairo -- sem passar por PNG em disco, que é o
que deixa o preview do Neovim mais lento a cada recompilação. As páginas são
desenhadas sob demanda: só a faixa visível chega a ser rasterizada.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Poppler", "0.18")

from gi.repository import Gdk, Gtk, Poppler

ESPACO_ENTRE_PAGINAS = 12


class Preview(Gtk.Box):
    """Rolagem vertical contínua das páginas do PDF."""

    __gtype_name__ = "SerifaPreview"

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self._documento: Poppler.Document | None = None
        self._zoom = 1.0
        self._ajustar_largura = True
        self._caminho: Path | None = None

        self._area = Gtk.DrawingArea()
        self._area.set_draw_func(self._desenhar)

        self._rolagem = Gtk.ScrolledWindow()
        self._rolagem.add_css_class("serifa-prova")
        self._rolagem.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._rolagem.set_child(self._area)
        self._rolagem.set_vexpand(True)
        self._rolagem.get_hadjustment().connect("changed", self._ao_mudar_largura)

        self._vazio = Gtk.Label()
        self._vazio.set_markup(
            "<span size='large'>Sem PDF ainda</span>\n"
            "<span alpha='60%'>Ctrl+B compila</span>"
        )
        self._vazio.set_justify(Gtk.Justification.CENTER)
        self._vazio.set_vexpand(True)

        self._pilha = Gtk.Stack()
        self._pilha.add_named(self._vazio, "vazio")
        self._pilha.add_named(self._rolagem, "pdf")
        self._pilha.set_vexpand(True)
        self.append(self._pilha)

        # Ctrl+scroll dá zoom, como em qualquer visualizador.
        rolinha = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        rolinha.connect("scroll", self._ao_rolar)
        self._area.add_controller(rolinha)

    # ----------------------------------------------------------- documento

    def carregar(self, caminho: str | Path) -> bool:
        caminho = Path(caminho)
        if not caminho.exists():
            return False

        posicao = self._rolagem.get_vadjustment().get_value()
        try:
            self._documento = Poppler.Document.new_from_file(caminho.as_uri(), None)
        except Exception:
            return False

        self._caminho = caminho
        self._pilha.set_visible_child_name("pdf")
        self._remedir()
        # Recompilar não deve jogar o leitor de volta para o topo.
        self._rolagem.get_vadjustment().set_value(posicao)
        return True

    def recarregar(self) -> bool:
        return self.carregar(self._caminho) if self._caminho else False

    @property
    def paginas(self) -> int:
        return self._documento.get_n_pages() if self._documento else 0

    # ---------------------------------------------------------------- zoom

    def aplicar_zoom(self, fator: float) -> None:
        self._ajustar_largura = False
        self._zoom = max(0.2, min(6.0, self._zoom * fator))
        self._remedir()

    def ajustar_a_largura(self) -> None:
        self._ajustar_largura = True
        self._remedir()

    @property
    def zoom(self) -> float:
        return self._zoom

    def _ao_rolar(self, controlador, dx: float, dy: float) -> bool:
        estado = controlador.get_current_event_state()
        if estado & Gdk.ModifierType.CONTROL_MASK:
            self.aplicar_zoom(0.9 if dy > 0 else 1.1)
            return True
        return False

    def _ao_mudar_largura(self, *_args) -> None:
        if self._ajustar_largura:
            self._remedir()

    # ------------------------------------------------------------- desenho

    def _tamanho_da_pagina(self, indice: int) -> tuple[float, float]:
        return self._documento.get_page(indice).get_size()

    def _escala(self) -> float:
        if not self._documento:
            return self._zoom
        if self._ajustar_largura:
            disponivel = self._rolagem.get_width()
            if disponivel > 1:
                largura, _ = self._tamanho_da_pagina(0)
                self._zoom = max(0.2, (disponivel - 2 * ESPACO_ENTRE_PAGINAS) / largura)
        return self._zoom

    def _remedir(self) -> None:
        if not self._documento:
            return
        escala = self._escala()
        largura = 0.0
        altura = float(ESPACO_ENTRE_PAGINAS)
        for i in range(self.paginas):
            p_largura, p_altura = self._tamanho_da_pagina(i)
            largura = max(largura, p_largura * escala)
            altura += p_altura * escala + ESPACO_ENTRE_PAGINAS
        self._area.set_content_width(int(largura + 2 * ESPACO_ENTRE_PAGINAS))
        self._area.set_content_height(int(altura))
        self._area.queue_draw()

    def _desenhar(self, area: Gtk.DrawingArea, ctx, largura: int, altura: int) -> None:
        if not self._documento:
            return

        escala = self._zoom
        ajuste = self._rolagem.get_vadjustment()
        topo_visivel = ajuste.get_value()
        base_visivel = topo_visivel + ajuste.get_page_size()

        y = float(ESPACO_ENTRE_PAGINAS)
        for i in range(self.paginas):
            p_largura, p_altura = self._tamanho_da_pagina(i)
            desenhada_largura = p_largura * escala
            desenhada_altura = p_altura * escala
            x = (largura - desenhada_largura) / 2

            # Só rasteriza o que está (quase) à vista.
            if y + desenhada_altura >= topo_visivel - 200 and y <= base_visivel + 200:
                ctx.save()
                # Fio em volta da folha, não sombra difusa: a sombra cinza
                # sob tudo é o clichê que faz qualquer interface parecer um
                # amontoado de cartões. Aqui a página tem borda porque papel
                # tem borda.
                ctx.set_source_rgba(0, 0, 0, 0.28)
                ctx.rectangle(x - 1, y - 1, desenhada_largura + 2, desenhada_altura + 2)
                ctx.fill()
                # O papel é sempre branco, mesmo no tema escuro: é o que o
                # professor vai ver impresso.
                ctx.set_source_rgb(1, 1, 1)
                ctx.rectangle(x, y, desenhada_largura, desenhada_altura)
                ctx.fill()
                ctx.translate(x, y)
                ctx.scale(escala, escala)
                self._documento.get_page(i).render(ctx)
                ctx.restore()

            y += desenhada_altura + ESPACO_ENTRE_PAGINAS

    # ------------------------------------------------------------ navegação

    def ir_para_pagina(self, numero: int) -> None:
        if not self._documento:
            return
        escala = self._zoom
        y = float(ESPACO_ENTRE_PAGINAS)
        for i in range(max(0, min(numero, self.paginas) - 1)):
            _, p_altura = self._tamanho_da_pagina(i)
            y += p_altura * escala + ESPACO_ENTRE_PAGINAS
        self._rolagem.get_vadjustment().set_value(y - ESPACO_ENTRE_PAGINAS)

    @property
    def pagina_atual(self) -> int:
        if not self._documento:
            return 0
        alvo = self._rolagem.get_vadjustment().get_value()
        escala = self._zoom
        y = float(ESPACO_ENTRE_PAGINAS)
        for i in range(self.paginas):
            _, p_altura = self._tamanho_da_pagina(i)
            y += p_altura * escala + ESPACO_ENTRE_PAGINAS
            if y > alvo + 40:
                return i + 1
        return self.paginas
