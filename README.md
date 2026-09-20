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
| **Modo vim** | Botão `VIM` na barra de título, ou `Ctrl+Alt+V`. A barra de estado mostra o que o vim reporta (`-- INSERT --`, `:w`, `/busca`, e o comando em digitação). O estado fica guardado entre sessões. Com o vim ligado, `Ctrl+B` e `Ctrl+I` são devolvidos a ele. |
| **Text objects no visual** | `vi{`, `va(`, `vi"` e afins, que o GtkSourceView não implementa — ver as armadilhas abaixo. Entende aninhamento e ignora chave escapada (`\{`), que em LaTeX é chave literal. |
| **Preview** | Rolagem contínua, só rasteriza o que está à vista. `Ctrl+scroll` dá zoom, `Ctrl+0` ajusta à largura. Recompilar **não** joga a rolagem pro topo. |
| **Prévia contínua** | 1,4 s depois de você parar de digitar, **sem tocar no seu arquivo**: o buffer vai para um arquivo sombra no cache e é compilado de lá, com o diretório de trabalho na pasta do texto — é esse detalhe que mantém `\input{../../preambulo.tex}` resolvendo, já que o TeX resolve caminho relativo contra o diretório de trabalho e não contra o arquivo. |
| **Compilação** | `Ctrl+B` ou `F5`: grava o seu `.tex` e compila ele mesmo, pelo `scripts/compilar.sh` do projeto quando existe — é ele que sabe nomear o PDF pela pasta. |
| **Salvar** | `Ctrl+S` grava e compila. Nada mais escreve no seu arquivo: gravar é sempre decisão sua. Fechar com alterações pendentes pergunta antes. |
| **Erros** | O `.log` é lido e desdobrado (o TeX quebra as mensagens em 79 colunas). Erros e avisos viram lista; clicar pula pra linha. |
| **Completação geral** | 144 snippets de comandos, letras gregas e ambientes, com tab stops, mais as palavras do documento. É a nativa do GtkSourceView. |
| **Completação por contexto** | Dentro das chaves, um popup próprio: `\cite{` oferece as chaves dos `.bib` com o título ao lado, `\ref{` os `\label` do documento, `\begin{` os ambientes, `\input{` os `.tex` e `\includegraphics{` as imagens. Casamento por subsequência — `eif` acha `einstein_infeld`. Aceitar pula o `}`. |
| **Pares automáticos** | `{`, `[`, `(`, `$` fecham sozinhos com o cursor no meio; `\begin{x}` + Enter escreve o `\end{x}`. Convivem com o vim: em modo normal não há inserção de texto, então nada dispara. |
| **Sumário** | Seções do documento na lateral (`F9`), inclusive títulos que quebram linha. Clicar pula. |
| **Contagem** | Palavras de prosa na barra de estado — comandos, matemática e comentários fora da conta. |
| **Conferidor** | `Ctrl+Shift+C` roda o `scripts/conferir-texto.py` do projeto e mostra o resultado no painel de erros. |
| **Busca** | `Ctrl+F`, com volta ao início. |
| **Sessão** | Último arquivo, modo vim, compilação contínua e posição do divisor voltam ao abrir. |

## Atalhos

`Ctrl+O` abrir · `Ctrl+S` salvar e compilar · `Ctrl+Shift+S` salvar como ·
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

## Três armadilhas encontradas no caminho

Ficam registradas porque as duas custam horas e nenhuma aparece na documentação.

**1. `GtkSourceCompletionProvider` não é implementável em PyGObject.** O par
`populate_async`/`populate_finish` estoura em C. O backtrace do core diz onde:

```
#0  gtk_source_completion_context_set_proposals_for_provider
#1  gtk_source_completion_context_populate_cb      ← callback do GtkSourceView
#2..#10 pygi_closure / ffi                         ← o populate_finish em Python
#11 g_task_return_now
```

O `populate_cb` recebe um `result` que não é a GTask — daí os dois
`g_task_get_source_object: assertion 'G_IS_TASK (task)' failed` que aparecem
antes do estouro — e um `user_data` corrompido. A causa é o binding não ter como
repassar o `user_data` original de um `GAsyncReadyCallback` que chega por vfunc.
Acontece num provedor mínimo de três itens fixos, completando a task na hora ou
num idle, devolvendo valor ou booleano, com ou sem referência viva para a GTask.
Não há como contornar do lado Python.

Por isso a completação por contexto é um `Gtk.Popover` próprio, em
`serifa/contexto.py`. Custou mais código e deu de volta o que o provedor daria —
com uma vantagem: controlando a inserção, chaves como `einstein_infeld` não
dependem do que o scanner de palavras do `GtkSourceCompletionWords` considera
uma palavra.

**2. O `snippets.rng` do GtkSourceView mente.** O parser real:

- **exige** `_group`, `_name`, `_description` com underscore, e rejeita as
  formas sem;
- **rejeita** o atributo `version`, que o RNG declara obrigatório;
- **exige** `languages` no `<text>`, que o RNG declara opcional.

Errar qualquer um desses dá um `WARNING` no console e zero snippets carregados,
sem mais explicação. Por isso o `.snippets` é gerado em tempo de execução a
partir das listas em `serifa/complete.py`: uma fonte de verdade só.

**3. O modo visual do GtkSourceView não tem text objects.** Os símbolos da
biblioteca dizem isso sem rodeios: existem `gtk_source_vim_command_set_text_object`
e `gtk_source_vim_insert_set_text_object`, mas o estado visual só expõe `clone`,
`get_bounds`, `ignore_command`, `new` e `warp`. Por isso `ci{` funciona e `vi{`
não — ali o `i` é ignorado e o `{` vira o movimento "parágrafo anterior", que
apenas pula o cursor.

`serifa/blocos.py` implementa a delimitação, e `Editor._ao_teclar_no_vim`
reconhece a sequência `v` → `i`/`a` → sinal. O `v` segue para o vim, que entra
em modo visual de verdade; o `i` e o sinal são consumidos antes do filtro.

## Estrutura

```
serifa/
├── editor.py     GtkSource.View, vim, pares automáticos, ortografia
├── blocos.py     delimitação de blocos: o `i{` e `a(` que faltam no visual
├── preview.py    Poppler + cairo, rolagem contínua
├── build.py      latexmk assíncrono e leitura do .log
├── complete.py   geração dos snippets
├── contexto.py   completação por contexto: detecção, acervo e popup
├── window.py     a janela e as ações
└── main.py       Adw.Application
```

## Requisitos

Já presentes nesta máquina: `gtk4`, `gtksourceview5`, `libadwaita`,
`poppler-glib`, `python3-gobject`, `libspelling`, `latexmk`.

O `bin/serifa` chama `/usr/bin/python3.12` de propósito: o `gi` está no Python
do sistema, e o `python3` do PATH aqui é o do mise (3.14), que não o tem.
