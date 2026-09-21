r"""Compilação assíncrona e leitura do log do LaTeX.

Há dois modos, e a diferença entre eles é o que cada um escreve em disco.

- **Compilação** (Ctrl+B, Ctrl+S) grava o seu .tex e compila ele mesmo, pelo
  scripts/compilar.sh do projeto quando existe.
- **Prévia** (a contínua, enquanto se digita) não encosta no seu arquivo:
  despeja o buffer num arquivo sombra dentro do cache e compila de lá, com o
  diretório de trabalho na pasta do texto. É esse detalhe que faz
  ``\input{../../preambulo.tex}`` continuar resolvendo, já que o TeX resolve
  caminho relativo contra o diretório de trabalho, não contra o arquivo.

O processo roda por Gio.Subprocess para a janela não congelar durante os
segundos do latexmk. O log é lido do arquivo, não da saída do terminal, porque
no terminal o TeX quebra as mensagens em 79 colunas.
"""

from __future__ import annotations

import hashlib
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
    r"^(?:LaTeX|Package|Class)(?: (\S+))? Warning: (.+)$", re.MULTILINE
)
# "on input line 12" aparece no MEIO da mensagem tanto quanto no fim --
# "Reference `x' on input line 12 undefined." é a forma mais comum. Procurar
# só no fim perdia o número na maioria dos avisos.
LINHA_DE_ENTRADA = re.compile(r"on input line (\d+)")

# O TeX corta a saída em max_print_line, 79 por padrão, sem recuar a
# continuação. É o comprimento exato que diz "continua na próxima", e não a
# indentação -- a primeira tentativa aqui usava indentação e não juntava nada.
LARGURA_DO_TEX = 79
# "(./arquivo.tex" -- a pilha de arquivos que o TeX abre.
ABRE_ARQUIVO = re.compile(r"\((\.{0,2}/?[^()\s]*\.tex)")


def _desdobrar(bruto: str) -> str:
    """Refaz as linhas que o TeX cortou em 79 colunas.

    Decidir pelo comprimento da linha ORIGINAL, e não pelo da linha já
    juntada: uma mensagem quebrada em três pedaços tem os dois primeiros com
    79 caracteres, e olhar para o acumulado faria o terceiro ficar de fora.
    """
    juntadas: list[str] = []
    continuar = False
    for linha in bruto.split("\n"):
        if continuar and juntadas:
            juntadas[-1] += linha
        else:
            juntadas.append(linha)
        continuar = len(linha) == LARGURA_DO_TEX
    return "\n".join(juntadas)


def ler_log(caminho_do_log: Path) -> list[Diagnostico]:
    """Extrai erros e avisos de um .log do LaTeX."""
    try:
        bruto = caminho_do_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    texto = _desdobrar(bruto)

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
        pacote, mensagem = casamento.groups()
        if "Rerun" in mensagem:  # ruído: o latexmk já resolve sozinho
            continue
        onde = LINHA_DE_ENTRADA.search(mensagem)
        rotulo = f"{pacote}: {mensagem}" if pacote else mensagem
        diagnosticos.append(
            Diagnostico("aviso", rotulo.strip(), None,
                        int(onde.group(1)) if onde else None)
        )

    return diagnosticos


class Compilador(GObject.Object):
    """Roda o latexmk e avisa quando termina."""

    __gsignals__ = {
        "comecou": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        # (deu certo, caminho do pdf ou "", diagnósticos, era prévia)
        "terminou": (GObject.SignalFlags.RUN_FIRST, None, (bool, str, object, bool)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._processo: Gio.Subprocess | None = None
        self._pendente: tuple | None = None

    @property
    def ocupado(self) -> bool:
        return self._processo is not None

    # --------------------------------------------------------- os dois modos

    def compilar(self, arquivo_tex: Path) -> None:
        """Compila o arquivo do usuário, que já deve estar gravado."""
        pasta = arquivo_tex.parent
        script = self._script_do_projeto(pasta)
        if script is not None:
            argumentos = [str(script), str(pasta)]
            diretorio = str(script.parent.parent)
        else:
            argumentos = [
                "latexmk", "-pdf", "-interaction=nonstopmode",
                "-halt-on-error", "-synctex=1", arquivo_tex.name,
            ]
            diretorio = str(pasta)
        self._lancar(
            argumentos,
            diretorio,
            self._pdf_de(arquivo_tex, pasta),
            self._log_de(arquivo_tex, pasta),
            previa=False,
        )

    def compilar_previa(self, texto: str, arquivo_tex: Path) -> None:
        """Compila o buffer sem tocar no arquivo do usuário."""
        sombra = self.pasta_da_sombra(arquivo_tex.parent)
        try:
            sombra.mkdir(parents=True, exist_ok=True)
            (sombra / "previa.tex").write_text(texto, encoding="utf-8")
        except OSError as erro:
            self.emit("terminou", False, "", [Diagnostico("erro", str(erro))], True)
            return

        self._lancar(
            [
                "latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                f"-output-directory={sombra}", str(sombra / "previa.tex"),
            ],
            # O diretório de trabalho é o da pasta do texto, não o da sombra:
            # é o que mantém os caminhos relativos do documento resolvendo.
            str(arquivo_tex.parent),
            sombra / "previa.pdf",
            sombra / "previa.log",
            previa=True,
        )

    @staticmethod
    def pasta_da_sombra(pasta_do_texto: Path) -> Path:
        chave = hashlib.sha1(str(pasta_do_texto).encode()).hexdigest()[:12]
        return Path(GLib.get_user_cache_dir()) / "serifa" / "previa" / chave

    # ------------------------------------------------------------- execução

    def _lancar(
        self, argumentos: list[str], diretorio: str, pdf: Path, log: Path, previa: bool
    ) -> None:
        if self._processo is not None:
            # Uma de cada vez; a última pedida vence.
            self._pendente = (argumentos, diretorio, pdf, log, previa)
            return

        lanc = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
        )
        lanc.set_cwd(diretorio)
        try:
            self._processo = lanc.spawnv(argumentos)
        except GLib.Error as erro:
            self.emit("terminou", False, "", [Diagnostico("erro", str(erro))], previa)
            return

        self.emit("comecou", previa)
        self._processo.wait_async(None, self._ao_terminar, (pdf, log, previa))

    def _ao_terminar(self, processo: Gio.Subprocess, resultado, dados) -> None:
        pdf, log, previa = dados
        try:
            processo.wait_finish(resultado)
        except GLib.Error:
            pass
        self._processo = None

        diagnosticos = ler_log(log)
        tem_pdf = pdf.exists()
        # O latexmk devolve código de erro mesmo quando o PDF saiu; quem manda
        # é o arquivo existir e não haver erro no log.
        sucesso = tem_pdf and not any(d.severidade == "erro" for d in diagnosticos)
        self.emit("terminou", sucesso, str(pdf) if tem_pdf else "", diagnosticos, previa)

        if self._pendente is not None:
            pendente, self._pendente = self._pendente, None
            self._lancar(*pendente)

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
    def _pdf_de(arquivo_tex: Path, pasta: Path) -> Path:
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
