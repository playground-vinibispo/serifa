r"""Delimitação de blocos por par de sinais -- o que o vim chama text object.

Existe porque o modo visual do GtkSourceView não tem text objects. Os símbolos
da biblioteca deixam isso explícito: há ``gtk_source_vim_command_set_text_object``
e ``gtk_source_vim_insert_set_text_object``, mas o estado visual só expõe
``clone``, ``get_bounds``, ``ignore_command``, ``new`` e ``warp``. Daí ``ci{``
funcionar e ``vi{`` não: o ``i`` é ignorado e o ``{`` vira o movimento
"parágrafo anterior", que apenas pula o cursor.

O módulo é de funções puras de propósito: é a parte que dá para testar sem
janela, sem teclado e sem vim.
"""

from __future__ import annotations

PARES = {
    "{": ("{", "}"), "}": ("{", "}"), "B": ("{", "}"),
    "(": ("(", ")"), ")": ("(", ")"), "b": ("(", ")"),
    "[": ("[", "]"), "]": ("[", "]"),
    "<": ("<", ">"), ">": ("<", ">"),
}

ASPAS = {'"': '"', "'": "'", "`": "`"}


def _escapado(texto: str, posicao: int) -> bool:
    """Diz se o caractere está precedido por um número ímpar de barras.

    Em LaTeX ``\\{`` é uma chave literal e não abre bloco nenhum -- ignorar
    isso faria ``vi{`` casar com a chave errada em qualquer ``\\newcommand``.
    """
    barras = 0
    i = posicao - 1
    while i >= 0 and texto[i] == "\\":
        barras += 1
        i -= 1
    return barras % 2 == 1


def limites_do_bloco(
    texto: str, posicao: int, abre: str, fecha: str
) -> tuple[int, int] | None:
    """Acha o par que envolve `posicao`. Devolve (índice do abre, do fecha).

    Conta profundidade nos dois sentidos, então aninhamento funciona: com o
    cursor em `b`, ``{a {b} c}`` devolve o par interno.
    """
    if not texto:
        return None
    posicao = max(0, min(posicao, len(texto) - 1))

    # Cursor em cima do próprio abre: o bloco é o que começa ali.
    if texto[posicao] == abre and not _escapado(texto, posicao):
        inicio = posicao
    else:
        nivel = 0
        inicio = -1
        for i in range(posicao, -1, -1):
            if _escapado(texto, i):
                continue
            if texto[i] == fecha and i != posicao:
                nivel += 1
            elif texto[i] == abre:
                if nivel == 0:
                    inicio = i
                    break
                nivel -= 1
        if inicio < 0:
            return None

    nivel = 0
    for j in range(inicio + 1, len(texto)):
        if _escapado(texto, j):
            continue
        if texto[j] == abre:
            nivel += 1
        elif texto[j] == fecha:
            if nivel == 0:
                return inicio, j
            nivel -= 1
    return None


def limites_das_aspas(texto: str, posicao: int, aspa: str) -> tuple[int, int] | None:
    """Mesma ideia para aspas, que não aninham: conta paridade na linha."""
    inicio_da_linha = texto.rfind("\n", 0, posicao) + 1
    fim_da_linha = texto.find("\n", posicao)
    if fim_da_linha < 0:
        fim_da_linha = len(texto)

    ocorrencias = [
        i
        for i in range(inicio_da_linha, fim_da_linha)
        if texto[i] == aspa and not _escapado(texto, i)
    ]
    for a, b in zip(ocorrencias[::2], ocorrencias[1::2]):
        if a <= posicao <= b:
            return a, b
    return None


def alvo(texto: str, posicao: int, sinal: str, por_dentro: bool) -> tuple[int, int] | None:
    """Traduz `i{`, `a{`, `i"`... para o intervalo a selecionar.

    `por_dentro` é o `i` do vim; `False` é o `a`, que inclui os delimitadores.
    Devolve (início, fim) como offsets de seleção, no estilo do Python: o fim
    é exclusivo.
    """
    if sinal in PARES:
        abre, fecha = PARES[sinal]
        achado = limites_do_bloco(texto, posicao, abre, fecha)
    elif sinal in ASPAS:
        achado = limites_das_aspas(texto, posicao, sinal)
    else:
        return None

    if achado is None:
        return None
    inicio, fim = achado
    return (inicio + 1, fim) if por_dentro else (inicio, fim + 1)
