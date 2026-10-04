# Serifa

Um editor de LaTeX de mesa, nativo, com preview do PDF ao lado, completação e
modo vim num botão. Abra vários documentos em abas e ajuste o tema, a fonte
e a largura do texto para sua escrita.

![Serifa no tema claro, com dois documentos em abas e preview do PDF](docs/images/serifa-light.png)

<details>
<summary>Ver o tema escuro</summary>

![Serifa no tema escuro](docs/images/serifa-dark.png)

</details>

```sh
bin/serifa                     # abre o último arquivo da sessão anterior
bin/serifa caminho/texto.tex   # abre um arquivo
bin/serifa um.tex outro.tex    # abre os dois em abas
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

## Tipografia

Isto não é um editor de código, e por isso não há número de linha, régua de 80
colunas nem realce da linha atual — instrumentos de quem navega por endereço,
não de quem lê um argumento de cem palavras. A coluna de texto tem largura
inicial de 74 caracteres, com margens
recalculadas a cada realocação e quebra por palavra inteira. Fonte inicial:
JetBrains Mono, em 11,5 pt.

O menu **Aparência** permite alternar os temas claro e escuro, aumentar ou
reduzir a fonte e estreitar ou alargar a coluna. Essas preferências são
compartilhadas entre as abas, aplicadas a documentos novos e guardadas para a
próxima sessão. A fonte pode variar de 8 a 24 pt e a coluna de 40 a 100 caracteres.

## O que tem

| | |
|---|---|
| **Abas** | Cada documento mantém seu texto, histórico de desfazer e preview. Abrir novamente um arquivo seleciona a aba existente. `Ctrl+W` fecha a aba; alterações pendentes pedem confirmação. `Ctrl+PageDown` e `Ctrl+PageUp` alternam entre abas. |
| **Modo vim** | Botão `Vim` na barra de título, ou `Ctrl+Alt+V`. A barra de estado mostra o que o vim reporta (`-- INSERT --`, `:w`, `/busca`, e o comando em digitação). O estado fica guardado entre sessões. Com o vim ligado, `Ctrl+B` e `Ctrl+I` são devolvidos a ele. |
| **Text objects no visual** | `vi{`, `va(`, `vi"` e afins, que o GtkSourceView não implementa — ver as armadilhas abaixo. Entende aninhamento e ignora chave escapada (`\{`), que em LaTeX é chave literal. |
| **Preview** | Rolagem contínua, só rasteriza o que está à vista. `Ctrl+scroll` dá zoom, `Ctrl+0` ajusta à largura. A barra do PDF mostra página atual, total de páginas e zoom, com botões para ampliar, reduzir e ajustar à largura. Recompilar **não** joga a rolagem pro topo. |
| **Prévia contínua** | 1,4 s depois de você parar de digitar, **sem tocar no seu arquivo**: o buffer vai para um arquivo sombra no cache e é compilado de lá, com o diretório de trabalho na pasta do texto — é esse detalhe que mantém `\input{../../preambulo.tex}` resolvendo, já que o TeX resolve caminho relativo contra o diretório de trabalho e não contra o arquivo. |
| **Compilação** | `F5` ou `Ctrl+Enter`: grava o seu `.tex` e compila ele mesmo, pelo `scripts/compilar.sh` do projeto quando existe — é ele que sabe nomear o PDF pela pasta. |
| **Salvar** | `Ctrl+S` grava e compila. Nada mais escreve no seu arquivo: gravar é sempre decisão sua. Fechar com alterações pendentes pergunta antes. |
| **Erros** | O `.log` é lido e desdobrado (o TeX quebra as mensagens em 79 colunas). Erros e avisos viram lista; clicar pula pra linha. |
| **Completação geral** | 144 snippets de comandos, letras gregas e ambientes, com tab stops, mais as palavras do documento. É a nativa do GtkSourceView. |
| **Completação por contexto** | Dentro das chaves, um popup próprio: `\cite{` oferece as chaves dos `.bib` com o título ao lado, `\ref{` os `\label` do documento, `\begin{` os ambientes, `\input{` os `.tex` e `\includegraphics{` as imagens. Casamento por subsequência — `eif` acha `einstein_infeld`. Aceitar pula o `}`. |
| **Pares automáticos** | `{`, `[`, `(`, `$` fecham sozinhos com o cursor no meio; `\begin{x}` + Enter escreve o `\end{x}`. Convivem com o vim: em modo normal não há inserção de texto, então nada dispara. |
| **Sumário** | Seções do documento na lateral (`F9`), com títulos longos que quebram linha. A seção atual acompanha o cursor; clicar pula para ela. |
| **Contagem** | Palavras de prosa na barra de estado — comandos, matemática e comentários fora da conta. |
| **Conferidor** | `Ctrl+Shift+C` roda o `scripts/conferir-texto.py` do projeto e mostra o resultado no painel de erros. |
| **Busca** | `Ctrl+F`, com volta ao início. |
| **Arquivo mexido fora** | O arquivo aberto é vigiado. Sem alterações pendentes aqui, o editor recarrega sozinho preservando a posição do cursor. Havendo, aparece um aviso com botão **Recarregar** — nada é sobrescrito sem você mandar. |
| **Sessão** | Último arquivo, modo vim, compilação contínua, posição do divisor e preferências de aparência voltam ao abrir. A lista completa de abas ainda não é restaurada. |

## Atalhos

`Ctrl+O` abrir · `Ctrl+S` salvar e compilar · `Ctrl+Shift+S` salvar como ·
`F5`/`Ctrl+Enter` compilar · `Ctrl+B` negrito · `Ctrl+I` itálico · `Ctrl+F` buscar · `Ctrl+Alt+V` vim · `F9` sumário ·
`Ctrl+Shift+V` preview · `Ctrl+±` zoom do PDF · `Ctrl+0` ajustar à largura ·
`Ctrl+Shift+C` conferir · `Ctrl+W` fechar aba ·
`Ctrl+PageDown`/`Ctrl+PageUp` alternar abas

## Ortografia em português

O corretor depende de `libspelling` e de um dicionário de português instalado
no sistema. Sem eles, a aplicação funciona com a correção desativada.
No Fedora, instale o dicionário com:

```sh
sudo dnf install hunspell-pt
```

Na próxima abertura, o corretor procura `pt_BR`, `pt_PT` ou `pt`, nessa ordem.

## Três armadilhas encontradas no caminho

Ficam registradas porque custaram horas e nenhuma aparece na documentação.

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
`serifa/context.py`. Custou mais código e deu de volta o que o provedor daria —
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

`serifa/blocks.py` implementa a delimitação, e `Editor.handle_key` — chamado
pelo controlador que a janela instala em si mesma — reconhece a sequência
`v` → `i`/`a` → sinal. O `v` segue para o vim, que entra em modo visual de
verdade; o `i` e o sinal são consumidos antes do filtro.

## Desenvolvimento

```sh
bin/preparar          # cria o .venv e instala ruff e coverage
bin/conferir          # ruff, o mesmo que a CI roda
bin/testes            # a suíte
bin/testes --cobertura
bin/instalar-hooks    # opcional: pre-push roda os dois
```

O `bin/preparar` cria o venv com `--system-site-packages` sobre o Python do
sistema, e isso não é detalhe: o PyGObject vem do sistema, e um venv isolado
não enxergaria `gi`, GtkSourceView nem Poppler. Instalar PyGObject por pip
criaria uma segunda cópia cega às bibliotecas GObject instaladas. O efeito
colateral bom é que o `coverage` passa a rodar no mesmo interpretador dos
testes, o que antes era impossível.

A CI roda os dois em cada push e PR. Os testes que precisam de `latexmk` se
pulam sozinhos, para não baixar um texlive inteiro no runner; os de janela
rodam sob Xvfb, porque o GTK4 não tem backend offscreen.

Use `bin/testes --cobertura` para obter os números atuais. Os testes do preview
incluem navegação entre páginas e renderização depois da rolagem; a aparência
final também precisa de inspeção visual.

## Testes

```sh
bin/testes                    # tudo
bin/testes -v                 # verboso
bin/testes tests.test_blocks  # um módulo
```

A suíte usa `unittest` da biblioteca padrão no Python com acesso ao `gi` e às
bibliotecas gráficas do sistema. A duração depende do backend gráfico e das
ferramentas de compilação disponíveis.

O que os torna rápidos é não precisarem de `app.run()`: basta registrar a
aplicação, montar a janela, chamar `present()` e bombear o laço principal à
mão (`tests/support.py`). Nada toca em arquivo seu — cada caso ganha uma pasta
temporária, e o estado de sessão é desviado para lá.

Quando há `mutter` instalado, o `bin/testes` abre as janelas num mutter
headless próprio, com D-Bus próprio: nada aparece na sua tela nem rouba o foco
enquanto a suíte roda. `bin/testes --na-tela` roda na sessão atual, para ver.
Na CI, sem mutter, quem dá o servidor gráfico é o `xvfb-run`. Os testes
gráficos se pulam sozinhos quando não há servidor gráfico nenhum.

Se o backend gráfico escolhido pelo ambiente não funcionar com o mutter
headless, execute explicitamente com Wayland e renderização Cairo:

```sh
GDK_BACKEND=wayland GSK_RENDERER=cairo bin/testes
```

Vale dizer o que cada grupo guarda, porque quase todos nasceram de um bug que
já aconteceu:

| arquivo | o que protege |
|---|---|
| `test_blocks` | delimitação de `vi{`, com aninhamento e chave escapada do LaTeX |
| `test_context` | os seis contextos de completação, e o `.bib` lido de pastas acima |
| `test_build` | o desdobramento das 79 colunas do TeX e o número de linha dos avisos |
| `test_complete` | que o parser de snippets aceita o XML — errar é silencioso |
| `test_editor` | pares automáticos, contagem de prosa, `overwrite` do modo normal |
| `test_keys` | o Shift no meio de `vi{`, e que o balão nunca desliga o vim |
| `test_appearance` | que o mobiliário de código não volta, e a medida da coluna |
| `test_document` | o arquivo aberto, sem janela: gravar, recarregar, conflito |
| `test_file_lifecycle` | **digitar não grava**, a sombra fora do projeto, a guarda ao trocar |
| `test_formatting` | envoltórios, aceleradores cedendo ao vim, balão só por edição |
| `test_multiple_documents` | abertura de todos os arquivos solicitados e criação da aba inicial |
| `test_tabs` | documentos independentes, ações da aba ativa, fechamento e aparência compartilhada |
| `test_preview_scroll` | redesenho das páginas ao rolar e atualização da prévia ao abrir |
| `test_visual_workflow` | controles de aparência, sumário, indicadores do PDF e persistência |

## Estrutura

```
serifa/
├── document.py   ler, gravar, alterações pendentes e vigia do disco
├── editor.py     GtkSource.View, vim, pares automáticos, ortografia
├── formatting.py envoltórios de formatação e a tabela que os descreve
├── session.py    estado guardado entre sessões
├── appearance.py temas, tipografia e medida da coluna
├── blocks.py     delimitação de blocos no modo visual
├── preview.py    Poppler + cairo, rolagem, zoom e indicadores do PDF
├── build.py      latexmk assíncrono e leitura do .log
├── complete.py   geração dos snippets
├── context.py    completação por contexto: detecção, acervo e popup
├── window.py     interface, ações e ciclo de vida de um documento
├── workspace.py  janela com abas e preferências compartilhadas
├── main.py       Adw.Application e abertura de arquivos
└── data/styles/  esquemas de sintaxe claro e escuro
```

## Requisitos

A aplicação requer Python 3.12 ou superior com PyGObject e as bibliotecas do
sistema GTK4, GtkSourceView 5, libadwaita e Poppler (incluindo o binding Cairo).
Para compilar documentos, instale `latexmk` e uma distribuição TeX com os
pacotes usados no seu documento. `libspelling` e o dicionário de português são
opcionais. O desenvolvimento usa `uv`, Ruff e coverage.

O `bin/serifa` chama `/usr/bin/python3.12` de propósito: o `gi` está no Python
do sistema. Os scripts ainda fixam esse caminho; em sistemas com outra
versão, é necessário ajustá-los para o Python que tenha acesso aos bindings
GObject. A instalação por distribuição ainda precisa ser documentada.
