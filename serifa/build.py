"""Compilação assíncrona e leitura do log do LaTeX.

O processo roda por Gio.Subprocess para que a janela não congele durante os
segundos do latexmk. O log é lido depois, porque a saída do TeX no terminal é
pior que o arquivo .log -- ela quebra as mensagens em 79 colunas.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from gi.repository import Gio, GLib, GObject


@dataclass(frozen=True)
class Diagnostico:
    """Um erro ou aviso do LaTeX, já com arquivo e linha quando dá para saber."""

    severidade: str  # "erro" | "aviso"
    mensagem: str
    arquivo: str | None = None
    linha: int | None = None

    @property
    def icone(self) -> str:
        return "dialog-error-symbolic" if self.severidade == "erro" else "dialog-warning-symbolic"

    @property
    def resumo(self) -> str:
        onde = ""
        if self.arquivo:
            onde = f"{Path(self.arquivo).name}"
            if self.linha:
                onde += f":{self.linha}"
            onde += " — "
        return f"{onde}{self.mensagem}"


# "! Undefined control sequence." e amigos.
ERRO = re.compile(r"^! (.+)$", re.MULTILINE)
# "l.23 \foo" -- a linha que o TeX reporta logo depois do erro.
LINHA_DO_ERRO = re.compile(r"^l\.(\d+)", re.MULTILINE)
AVISO = re.compile(
    r"^(?:LaTeX|Package|Class)(?: (\S+))? Warning: (.+?)(?:\s+on input line (\d+))?\.?$",
    re.MULTILINE,
)
# "(./arquivo.tex" -- a pilha de arquivos que o TeX abre.
ABRE_ARQUIVO = re.compile(r"\((\.{0,2}/?[^()\s]*\.tex)")


def ler_log(caminho_do_log: Path) -> list[Diagnostico]:
    """Extrai erros e avisos de um .log do LaTeX."""
    try:
        bruto = caminho_do_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # O TeX quebra linhas longas em 79 colunas; juntar é o que torna as
    # mensagens legíveis de novo.
    texto = re.sub(r"\n(?! )", "\x00", bruto).replace("\n", "").replace("\x00", "\n")

    diagnosticos: list[Diagnostico] = []

    for casamento in ERRO.finditer(texto):
        mensagem = casamento.group(1).strip()
        resto = texto[casamento.end() : casamento.end() + 2000]
        linha = LINHA_DO_ERRO.search(resto)
        arquivo = None
        anterior = ABRE_ARQUIVO.findall(texto[: casamento.start()])
        if anterior:
            arquivo = anterior[-1]
        diagnosticos.append(
            Diagnostico(
                "erro",
                mensagem,
                arquivo,
                int(linha.group(1)) if linha else None,
            )
        )

    for casamento in AVISO.finditer(texto):
        pacote, mensagem, linha = casamento.groups()
        if "Rerun" in mensagem:  # ruído: o latexmk já resolve sozinho
            continue
        rotulo = f"{pacote}: {mensagem}" if pacote else mensagem
        diagnosticos.append(
            Diagnostico("aviso", rotulo.strip(), None, int(linha) if linha else None)
        )

    return diagnosticos


class Compilador(GObject.Object):
    """Roda o latexmk e avisa quando termina.

    Respeita o `scripts/compilar.sh` do projeto quando ele existe: é ele que
    sabe nomear o PDF pela pasta do trabalho.
    """

    __gsignals__ = {
        "comecou": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # (deu certo, caminho do pdf ou "", lista de diagnósticos)
        "terminou": (GObject.SignalFlags.RUN_FIRST, None, (bool, str, object)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._processo: Gio.Subprocess | None = None
        self._pendente = False

    @property
    def ocupado(self) -> bool:
        return self._processo is not None

    def compilar(self, arquivo_tex: Path) -> None:
        if self._processo is not None:
            self._pendente = True  # recompila assim que a atual terminar
            return

        pasta = arquivo_tex.parent
        script = self._script_do_projeto(pasta)
        if script is not None:
            argumentos = [str(script), str(pasta)]
            diretorio = str(script.parent.parent)
        else:
            argumentos = [
                "latexmk",
                "-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-synctex=1",
                arquivo_tex.name,
            ]
            diretorio = str(pasta)

        lanc = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
        )
        lanc.set_cwd(diretorio)
        try:
            self._processo = lanc.spawnv(argumentos)
        except GLib.Error as erro:
            self.emit("terminou", False, "", [Diagnostico("erro", str(erro))])
            return

        self.emit("comecou")
        self._processo.wait_async(None, self._ao_terminar, (arquivo_tex, pasta))

    def _ao_terminar(self, processo: Gio.Subprocess, resultado, dados) -> None:
        arquivo_tex, pasta = dados
        try:
            processo.wait_finish(resultado)
            deu_certo = processo.get_successful()
        except GLib.Error:
            deu_certo = False
        self._processo = None

        diagnosticos = ler_log(self._log_de(arquivo_tex, pasta))
        pdf = self._pdf_de(arquivo_tex, pasta)
        # O latexmk devolve código de erro mesmo quando o PDF saiu; quem manda
        # é o arquivo existir e não haver erro no log.
        tem_pdf = pdf is not None and pdf.exists()
        sucesso = tem_pdf and not any(d.severidade == "erro" for d in diagnosticos)

        self.emit("terminou", sucesso, str(pdf) if tem_pdf else "", diagnosticos)

        if self._pendente:
            self._pendente = False
            self.compilar(arquivo_tex)

    # ------------------------------------------------------------- caminhos

    @staticmethod
    def _script_do_projeto(pasta: Path) -> Path | None:
        """Sobe a árvore procurando um scripts/compilar.sh executável."""
        for candidata in [pasta, *pasta.parents]:
            script = candidata / "scripts" / "compilar.sh"
            if script.is_file() and os.access(script, os.X_OK):
                return script
        return None

    @staticmethod
    def _pdf_de(arquivo_tex: Path, pasta: Path) -> Path | None:
        # O compilar.sh nomeia o PDF pela pasta; o latexmk cru, pelo .tex.
        pelo_nome_da_pasta = pasta / f"{pasta.name}.pdf"
        if pelo_nome_da_pasta.exists():
            return pelo_nome_da_pasta
        return arquivo_tex.with_suffix(".pdf")

    @staticmethod
    def _log_de(arquivo_tex: Path, pasta: Path) -> Path:
        pelo_nome_da_pasta = pasta / f"{pasta.name}.log"
        if pelo_nome_da_pasta.exists():
            return pelo_nome_da_pasta
        return arquivo_tex.with_suffix(".log")
