# Contribuindo com o Serifa

O Serifa é um editor nativo de LaTeX para Linux, com preview de PDF e modo Vim.
Você pode ajudar com código, documentação, relatos de bugs, testes de instalação
em outras distribuições e avaliação dos fluxos de escrita.

## Comece por aqui

Leia a [instalação no README](README.md#instalação) e experimente abrir um
arquivo, editar e compilar com `F5`. Se não souber por onde começar, procure
[issues abertas](https://github.com/playground-vinibispo/serifa/issues) e
verifique se alguém já está trabalhando na mudança que você quer fazer.

Para mudanças maiores de comportamento ou arquitetura, abra uma issue com o
problema e a proposta antes de implementar. Correções pequenas e melhorias de
documentação podem seguir diretamente para um PR.

## Prepare o ambiente

Instale as bibliotecas gráficas do sistema e
[uv](https://docs.astral.sh/uv/getting-started/installation/). Depois, no seu
clone ou fork:

```sh
git clone https://github.com/playground-vinibispo/serifa.git
cd serifa
bin/python --check
bin/preparar
bin/serifa
```

Se você usa um fork, troque a URL de clone pela do seu repositório. Crie uma
branch para sua mudança:

```sh
git switch -c minha-contribuicao
```

`bin/preparar` cria um `.venv` que enxerga os bindings GObject do sistema e
instala as ferramentas nas versões de `uv.lock`. Não é necessário ativar o
venv: os scripts selecionam o interpretador automaticamente. Para escolher
outro Python, use `SERIFA_PYTHON=/caminho/python3` antes do comando; ele precisa
passar em `bin/python --check`.

A preparação pode ser repetida. Atualize `uv.lock` apenas quando a mudança
precisar atualizar dependências, usando `uv lock --upgrade` e revisando o diff.

## Verifique sua mudança

```sh
bin/conferir                   # Ruff
bin/testes                     # suíte completa
bin/testes tests.test_document # um módulo durante o desenvolvimento
bin/testes --cobertura         # relatório de cobertura
```

Os testes gráficos exigem um servidor gráfico. Com `mutter` instalado, o
script usa um compositor Wayland headless e um barramento D-Bus próprios.
Para inspecionar as janelas na sua sessão, use `bin/testes --na-tela`.

Outra opção é instalar Xvfb e executar como a CI:

```sh
SERIFA_ISOLADO=1 xvfb-run -a bin/testes
```

Sem servidor gráfico, os testes de janela são pulados. Sem `latexmk`, os
casos que exigem compilação também são pulados: uma execução com testes
pulados não confirma esses fluxos. Informe essa limitação no PR.

Para mudanças visuais, confira também a aplicação aberta: temas claro e
escuro, abas, editor, sumário e PDF. Se alterar o ciclo de vida de documentos,
verifique salvar, descartar e cancelar ao fechar com alterações pendentes.

Corrija ou acrescente um teste de regressão quando mudar comportamento. Para
uma alteração apenas de documentação, confira exemplos, links e a coerência
com os scripts atuais.

Opcionalmente, ative o hook que roda lint e testes antes de cada push:

```sh
bin/instalar-hooks
```

Para desativá-lo, use `git config --unset core.hooksPath`.

## Onde mexer

| Área | Arquivos principais |
|---|---|
| Abrir, salvar e monitorar arquivos | `serifa/document.py` |
| Edição, Vim e pares automáticos | `serifa/editor.py`, `serifa/blocks.py` |
| Completação | `serifa/complete.py`, `serifa/context.py` |
| Compilação e diagnósticos | `serifa/build.py` |
| Renderização e navegação do PDF | `serifa/preview.py` |
| Temas, fonte e largura do texto | `serifa/appearance.py`, `serifa/data/styles/` |
| Interface de um documento e abas | `serifa/window.py`, `serifa/workspace.py` |
| Abertura da aplicação e sessão | `serifa/main.py`, `serifa/session.py` |
| Instalação e execução | `bin/`, `.github/workflows/ci.yml` |

O código usa nomes em inglês, Python, PyGObject e widgets GTK4/libadwaita.
Siga o estilo do módulo que estiver alterando. Os bindings gráficos vêm do
sistema; preserve a seleção de versões com `gi.require_version()` antes dos
imports de `gi.repository`.

Use `unittest`, como o restante da suíte. Para testes de janela, reutilize
`GraphicalCase` e as funções de `tests/support.py`: elas isolam arquivos e
estado de sessão em diretórios temporários.

## Abra um pull request

Mantenha o PR focado em um problema. Descreva:

- O problema e o comportamento que mudou.
- Como reproduzir ou experimentar a mudança.
- Os comandos de validação e os resultados, incluindo testes pulados.
- Screenshots dos temas afetados, quando houver mudança visual.
- A issue relacionada, se existir.

Evite incluir `.venv`, caches, arquivos pessoais e PDFs gerados pelos seus
textos. Confira `git diff --check` e `git status` antes de publicar.

A CI executa Ruff e a suíte gráfica no Ubuntu 24.04. Responda aos comentários
de revisão e atualize a mesma branch para manter a discussão no PR original.

## Relate bugs e sugira melhorias

[Abra uma issue](https://github.com/playground-vinibispo/serifa/issues/new) com
passos para reproduzir, resultado esperado e resultado observado. Inclua a
distribuição, a versão do Serifa ou commit e a saída de `bin/python --check`.
Para problemas de compilação, inclua também `latexmk --version`.

Um `.tex` mínimo e a mensagem de erro ajudam mais que um documento inteiro.
Remova informações pessoais dos exemplos e logs antes de publicar. Para uma
sugestão, explique a tarefa de escrita que você quer realizar e onde encontra
atrito hoje.

## Licença das contribuições

As contribuições de código ao Serifa são recebidas sob a mesma licença do
projeto, [GPL-3.0-only](LICENSE). Ao enviar uma contribuição, confirme que você
tem direito de disponibilizá-la nesses termos. Preserve os avisos existentes e
identifique a licença e a origem de código de terceiros, quando houver.
