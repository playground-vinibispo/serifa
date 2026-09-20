# Serifa

Um editor de LaTeX de mesa, nativo, com preview do PDF ao lado, completação e
modo vim num botão.

```sh
bin/serifa                     # abre o último arquivo da sessão anterior
bin/serifa caminho/texto.tex   # abre um arquivo
```

## Por que GTK4 e não Electron ou Tauri

Um editor de texto é feito de três coisas caras: leiaute de texto, realce de
sintaxe e rasterização de PDF. Aqui as três são C:

- **GtkSourceView 5** é o motor do GNOME Text Editor e do Builder. Traz o realce
  de LaTeX, os snippets, a completação e — o ponto que decidiu a escolha — uma
  **emulação de vim escrita em C** (`GtkSourceVimIMContext`), a mesma do Builder.
  Reimplementar isso em JavaScript seria trocar o certo pelo duvidoso.
- **Poppler** rasteriza o PDF direto em cairo, sem passar por PNG em disco.
- **Python** só amarra os eventos. Nada de laço quente passa por ele.

Tauri poria um WebView entre você e o texto. Se um dia o Python incomodar, o
caminho é gtk-rs: mesmos widgets, mesma aparência, sem trocar de arquitetura.

## O que tem

| | |
|---|---|
| **Modo vim** | Botão `VIM` na barra de título, ou `Ctrl+Alt+V`. A barra de comandos (`:w`, `/busca`) aparece na barra de estado. O estado fica guardado entre sessões. |
| **Preview** | Rolagem contínua, só rasteriza o que está à vista. `Ctrl+scroll` dá zoom, `Ctrl+0` ajusta à largura. Recompilar **não** joga a rolagem pro topo. |
| **Compilação** | `Ctrl+B` ou `F5`, assíncrona. Usa o `scripts/compilar.sh` do projeto quando existe — é ele que sabe nomear o PDF pela pasta. Contínua por padrão: 1,4 s depois de você parar de digitar. |
| **Erros** | O `.log` é lido e desdobrado (o TeX quebra as mensagens em 79 colunas). Erros e avisos viram lista; clicar pula pra linha. |
| **Completação** | 144 snippets de comandos, letras gregas e ambientes, com tab stops. Mais as palavras do documento e as chaves dos `.bib` do projeto. |
| **Pares automáticos** | `{`, `[`, `(`, `$` fecham sozinhos com o cursor no meio; `\begin{x}` + Enter escreve o `\end{x}`. Convivem com o vim: em modo normal não há inserção de texto, então nada dispara. |
| **Sumário** | Seções do documento na lateral (`F9`), inclusive títulos que quebram linha. Clicar pula. |
| **Contagem** | Palavras de prosa na barra de estado — comandos, matemática e comentários fora da conta. |
| **Conferidor** | `Ctrl+Shift+C` roda o `scripts/conferir-texto.py` do projeto e mostra o resultado no painel de erros. |
| **Busca** | `Ctrl+F`, com volta ao início. |
| **Sessão** | Último arquivo, modo vim, compilação contínua e posição do divisor voltam ao abrir. |

## Atalhos

`Ctrl+O` abrir · `Ctrl+S` salvar (e compilar) · `Ctrl+Shift+S` salvar como ·
`Ctrl+B`/`F5` compilar · `Ctrl+F` buscar · `Ctrl+Alt+V` vim · `F9` sumário ·
`Ctrl+Shift+V` preview · `Ctrl+±` zoom do PDF · `Ctrl+0` ajustar à largura ·
`Ctrl+Shift+C` conferir

## Ortografia em português

Está ligada no código, mas **não há dicionário de português instalado** nesta
máquina — o Enchant lista 24 idiomas e nenhum `pt`. Sem dicionário o corretor
fica desligado de propósito: corrigir em inglês um texto todo em português é
pior que não corrigir. Para ligar:

```sh
sudo dnf install hunspell-pt
```

Na próxima abertura o `Spelling` acha `pt_BR` sozinho.

## Duas armadilhas encontradas no caminho

Ficam registradas porque as duas custam horas e nenhuma aparece na documentação.

**1. Provedor de completação próprio segfaulta.** O par
`populate_async`/`populate_finish` do GtkSourceView 5.14 estoura em C logo
depois que `populate_finish` devolve o modelo, sem frame Python no backtrace.
Acontece até num provedor mínimo de três itens fixos, com ou sem referência viva
para a GTask, devolvendo valor ou booleano. É bug de binding. A completação
sensível ao contexto (oferecer chaves de `.bib` só dentro de `\cite{`) morreu
com ele; o que sobrou usa as peças em C, que não passam por vfunc de Python.

**2. O `snippets.rng` do GtkSourceView mente.** O parser real:

- **exige** `_group`, `_name`, `_description` com underscore, e rejeita as
  formas sem;
- **rejeita** o atributo `version`, que o RNG declara obrigatório;
- **exige** `languages` no `<text>`, que o RNG declara opcional.

Errar qualquer um desses dá um `WARNING` no console e zero snippets carregados,
sem mais explicação. Por isso o `.snippets` é gerado em tempo de execução a
partir das listas em `serifa/complete.py`: uma fonte de verdade só.

## Estrutura

```
serifa/
├── editor.py     GtkSource.View, vim, pares automáticos, ortografia
├── preview.py    Poppler + cairo, rolagem contínua
├── build.py      latexmk assíncrono e leitura do .log
├── complete.py   geração dos snippets e as chaves de .bib
├── window.py     a janela e as ações
└── main.py       Adw.Application
```

## Requisitos

Já presentes nesta máquina: `gtk4`, `gtksourceview5`, `libadwaita`,
`poppler-glib`, `python3-gobject`, `libspelling`, `latexmk`.

O `bin/serifa` chama `/usr/bin/python3.12` de propósito: o `gi` está no Python
do sistema, e o `python3` do PATH aqui é o do mise (3.14), que não o tem.
