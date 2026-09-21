"""Completação.

Uma nota sobre o caminho que *não* foi tomado. A forma elegante seria um
GtkSourceCompletionProvider próprio, que enxerga o contexto à esquerda do
cursor e decide se oferece comandos, ambientes, chaves de citação ou rótulos.
Ela chegou a ficar pronta e a detecção de contexto funcionava -- até o popup
aparecer: o par ``populate_async``/``populate_finish`` do GtkSourceView 5.14
estoura em C logo depois de ``populate_finish`` devolver o modelo, sem frame
Python no backtrace. É bug de binding, não de uso: o mesmo estouro acontece
num provedor mínimo de três itens fixos, com ou sem referência viva para a
GTask, devolvendo valor ou booleano.

Então a completação é montada com as duas peças que o GtkSourceView já traz
prontas, ambas em C:

- ``GtkSourceCompletionSnippets``, alimentado por um .snippets gerado aqui a
  partir das listas abaixo -- comandos e ambientes, com tab stops;
- ``GtkSourceCompletionWords``, alimentado pelo próprio documento e por um
  buffer invisível com as chaves dos .bib e os ``\\label`` do texto.

Perde-se a consciência de contexto: as chaves de citação aparecem em qualquer
lugar, não só dentro de ``\\cite{``. Ganha-se não derrubar o editor.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")

from gi.repository import GLib, Gtk

# (gatilho, texto do snippet). $1, $2 são tab stops; $0 é onde o cursor para.
COMANDOS: list[tuple[str, str]] = [
    ("documentclass", "\\documentclass[${1:12pt, a4paper}]{${2:article}}$0"),
    ("usepackage", "\\usepackage{$1}$0"),
    ("section", "\\section{$1}\n$0"),
    ("sectionx", "\\section*{$1}\n$0"),
    ("subsection", "\\subsection{$1}\n$0"),
    ("subsectionx", "\\subsection*{$1}\n$0"),
    ("subsubsection", "\\subsubsection{$1}\n$0"),
    ("paragraph", "\\paragraph{$1}$0"),
    ("chapter", "\\chapter{$1}\n$0"),
    ("title", "\\title{$1}$0"),
    ("author", "\\author{$1}$0"),
    ("maketitle", "\\maketitle$0"),
    ("textbf", "\\textbf{$1}$0"),
    ("textit", "\\textit{$1}$0"),
    ("texttt", "\\texttt{$1}$0"),
    ("textsc", "\\textsc{$1}$0"),
    ("emph", "\\emph{$1}$0"),
    ("underline", "\\underline{$1}$0"),
    ("footnote", "\\footnote{$1}$0"),
    ("enquote", "\\enquote{$1}$0"),
    ("label", "\\label{$1}$0"),
    ("ref", "\\ref{$1}$0"),
    ("eqref", "\\eqref{$1}$0"),
    ("pageref", "\\pageref{$1}$0"),
    ("cite", "\\cite{$1}$0"),
    ("citep", "\\citep{$1}$0"),
    ("citet", "\\citet{$1}$0"),
    ("bibliography",
     "\\bibliographystyle{${1:unsrt}}\n\\bibliography{${2:../../referencias}}$0"),
    ("input", "\\input{$1}$0"),
    ("include", "\\include{$1}$0"),
    ("includegraphics", "\\includegraphics[width=${1:0.8\\textwidth}]{$2}$0"),
    ("caption", "\\caption{$1}$0"),
    ("item", "\\item $0"),
    ("frac", "\\frac{$1}{$2}$0"),
    ("sqrt", "\\sqrt{$1}$0"),
    ("sum", "\\sum_{$1}^{$2}$0"),
    ("int", "\\int_{$1}^{$2}$0"),
    ("lim", "\\lim_{$1}$0"),
    ("newcommand", "\\newcommand{$1}{$2}$0"),
    ("renewcommand", "\\renewcommand{$1}{$2}$0"),
    ("linespread", "\\linespread{$1}$0"),
    ("setlength", "\\setlength{$1}{$2}$0"),
    ("vspace", "\\vspace{$1}$0"),
    ("hspace", "\\hspace{$1}$0"),
    ("newpage", "\\newpage$0"),
    ("clearpage", "\\clearpage$0"),
    ("partial", "\\partial$0"),
    ("infty", "\\infty$0"),
    ("cdot", "\\cdot$0"),
    ("times", "\\times$0"),
    ("approx", "\\approx$0"),
    ("neq", "\\neq$0"),
    ("leq", "\\leq$0"),
    ("geq", "\\geq$0"),
    ("ldots", "\\ldots$0"),
    ("quad", "\\quad$0"),
    ("rightarrow", "\\rightarrow$0"),
    ("Rightarrow", "\\Rightarrow$0"),
]

LETRAS_GREGAS = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau",
    "phi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi",
    "Pi", "Sigma", "Phi", "Psi", "Omega",
]

AMBIENTES = [
    "document", "abstract", "itemize", "enumerate", "description",
    "figure", "table", "tabular", "center", "flushleft", "flushright",
    "quote", "quotation", "verse", "verbatim", "equation", "equationx",
    "align", "alignx", "gather", "matrix", "pmatrix", "bmatrix",
    "cases", "array", "minipage", "thebibliography",
]

CHAVE_BIB = re.compile(r"@\w+\s*\{\s*([^,\s]+)", re.MULTILINE)
ROTULO = re.compile(r"\\label\{([^}]+)\}")


def _snippet(gatilho: str, descricao: str, texto: str) -> str:
    # O parser do GtkSourceView contraria o próprio snippets.rng em três
    # pontos, todos descobertos na tentativa e erro: exige as formas com
    # underscore (_group, _name, _description) e rejeita as sem; rejeita o
    # atributo version, que o RNG declara obrigatório; e exige languages no
    # <text>, que o RNG declara opcional. Mexer aqui sem testar quebra tudo
    # de uma vez, em silêncio -- o erro é só um WARNING no console.
    return (
        f'  <snippet _name="{escape(gatilho)}" trigger="{escape(gatilho)}"\n'
        f'           _description="{escape(descricao)}">\n'
        f'    <text languages="latex;"><![CDATA[{texto}]]></text>\n'
        f"  </snippet>\n"
    )


def preparar_snippets() -> Path:
    """Gera o .snippets a partir das listas acima e devolve a pasta.

    Gerado em tempo de execução de propósito: a lista Python fica sendo a
    única fonte de verdade, e não há XML para esquecer de atualizar.
    """
    pasta = Path(GLib.get_user_cache_dir()) / "serifa" / "snippets"
    pasta.mkdir(parents=True, exist_ok=True)

    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>\n<snippets _group="LaTeX">\n'
    ]
    for gatilho, texto in COMANDOS:
        partes.append(_snippet(gatilho, texto.replace("$0", "").strip(), texto))
    for letra in LETRAS_GREGAS:
        partes.append(_snippet(letra, f"\\{letra}", f"\\{letra}$0"))
    for ambiente in AMBIENTES:
        # "equationx" é o gatilho de equation*: asterisco não vale como gatilho.
        real = ambiente[:-1] + "*" if ambiente.endswith("x") else ambiente
        corpo = f"\\begin{{{real}}}\n  $1\n\\end{{{real}}}$0"
        partes.append(_snippet(ambiente, f"ambiente {real}", corpo))
        partes.append(_snippet(f"beg{ambiente}", f"ambiente {real}", corpo))
    partes.append("</snippets>\n")

    (pasta / "latex.snippets").write_text("".join(partes), encoding="utf-8")
    return pasta


class FonteDeChaves:
    """Buffer invisível com as chaves dos .bib e os rótulos do documento.

    Alimenta o GtkSourceCompletionWords, que só completa palavras existentes
    em algum buffer registrado nele.
    """

    def __init__(self) -> None:
        self.buffer = Gtk.TextBuffer()
        self._pasta: Path | None = None
        self._chaves_bib: list[str] = []

    def definir_pasta(self, pasta: Path | None) -> None:
        if pasta == self._pasta:
            return
        self._pasta = pasta
        self._chaves_bib = self._ler_bibs(pasta) if pasta else []

    def atualizar(self, texto_do_documento: str) -> None:
        rotulos = sorted(set(ROTULO.findall(texto_do_documento)))
        self.buffer.set_text("\n".join([*self._chaves_bib, *rotulos]))

    @property
    def chaves(self) -> list[str]:
        return list(self._chaves_bib)

    @staticmethod
    def _ler_bibs(pasta: Path) -> list[str]:
        encontradas: list[str] = []
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
                    texto = arquivo.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for chave in CHAVE_BIB.findall(texto):
                    if chave not in vistas:
                        vistas.add(chave)
                        encontradas.append(chave)
        return encontradas
