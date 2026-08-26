
# Nordex Comparador

App desktop com interface gráfica para `python/gerar_base.py`: você seleciona
os dois exports SAP ("Administrar itens de fornecedor" e "Partidas individuais
no Razão") e uma pasta de saída, o app roda o script Python e mostra o
relatório `Payments_<data>.xlsx` gerado (mesmo layout de `Resumo` / `Base` /
uma aba por produto / `Validações` que o script já produzia).

`gerar_base.py`, `regras.py` e `config.py` não tiveram a lógica de negócio
alterada — só foi adicionado suporte a `--file1` / `--file2` / `--output-dir`
em `gerar_base.py` (ver seu `Uso:` no topo do arquivo) para que a UI possa
passar os caminhos escolhidos em vez de depender da pasta `entrada/`. Rodar o
script direto do terminal sem esses argumentos continua funcionando como antes.

Tem duas interfaces, mesma lógica por baixo — escolha a que servir na sua
máquina:

- **`src/` (Electron)** — precisa de Node/npm instalado.
- **`python/gui.py` (Tkinter)** — só precisa do Python (Tkinter já vem junto
  do instalador do Python no Windows). Use esta se a máquina não tiver Node.

## Alternativa sem Node — `python/gui.py`

```bash
cd python
pip install -r requirements.txt
python gui.py
```

Mesma tela (seleção dos 2 arquivos, pasta de saída, botão de executar, console
que só aparece se der erro, cartão de sucesso com os valores analisados).
Chama `gerar_base.main(...)` direto (mesmo processo, numa thread) — não
depende de `sys.executable`/subprocess, o que é o que permite empacotar tudo
num único `.exe` (próxima seção).

Em algumas distros Linux o Tkinter é um pacote à parte do Python
(`sudo apt install python3-tk` / `python3.11-tk` conforme sua versão). No
instalador oficial do Windows (python.org) já vem incluído.

### Gerar um `.exe` standalone (sem precisar de Python na máquina que for usar)

Na máquina que **tem** Python (a mesma que já roda `gui.py` hoje):

```bash
cd python
build_exe.bat
```

Isso empacota `gui.py` + `gerar_base.py`/`regras.py`/`config.py` +
`pandas`/`openpyxl`/Tkinter + o logo, tudo num único
`dist\NordexComparador.exe`. Duplo-clique abre a interface direto — nada de
terminal, nada de Python instalado na máquina que for rodar. Só precisa gerar
de novo se o código mudar; o `.exe` em si pode ser copiado pra qualquer PC
Windows.

`build_exe.bat` tenta achar o Python sozinho, nesta ordem, e não precisa
abrir o "WinPython Command Prompt" na mão antes:

1. Caminho passado na linha de comando (`build_exe.bat "C:\...\python.exe"`).
2. Alguns caminhos conhecidos na Área de Trabalho/perfil do usuário
   (resolvendo redirecionamento pro OneDrive quando existir), testando tanto
   `<pasta>\python.exe` quanto `<pasta>\python\python.exe` — o WinPython
   costuma usar a segunda forma (subpasta `python\` aninhada), mas instalações
   portáteis mais simples às vezes têm o `.exe` direto na raiz.
3. Varredura de pastas `WPy*` / `Python*` / `WinPython*` na Área de Trabalho e
   no perfil, nos mesmos dois formatos acima.
4. `python`/`python3` do PATH do sistema, como último recurso.

Se nada disso encontrar um interpretador, ele avisa e para, mostrando o
comando exato pra rodar passando o caminho manualmente.

O `.exe` costuma sair grande (150–250 MB) porque leva o Python inteiro +
pandas/numpy dentro — normal para esse tipo de empacotamento, não é bug.

**Importante:** rode `build_exe.bat` sempre de dentro da pasta `python/`
(onde estão `gui.py`, `requirements.txt`, `assets/`) — nunca de dentro da
pasta raiz da instalação do Python. Ele usa `requirements.txt` e `assets/`
relativos à própria localização do script; rodando do lugar errado, o
PyInstaller não encontra esses arquivos e o build falha ou gera um `.exe`
incompleto.

## Electron — pré-requisitos

- Node.js 18+
- Python 3.10+ com `pandas` e `openpyxl` (o app detecta `python3`/`python` no
  PATH automaticamente; se não encontrar, pede pra você localizar o
  executável manualmente na primeira execução — essa escolha fica salva)

## Setup

```bash
# dependências do Electron
npm install

# dependências do script Python
pip install -r python/requirements.txt
```

## Rodar em desenvolvimento

```bash
npm start
```

## Empacotar (Windows)

```bash
npm run build
```

Gera o instalador em `dist/`. A pasta `python/` (scripts + `requirements.txt`)
é empacotada junto em `resources/python`; o Python em si **não** é empacotado —
a máquina que for rodar o instalador precisa ter Python com `pandas`/`openpyxl`
instalados (ou você aponta o app para um Python específico na tela inicial).

## Como exportar os dois relatórios do SAP (importante)

O resultado depende dos filtros do export. A variante validada em 19.08.2026
("MICHAEL - BUSCA GERAL (V2)", salva com estes filtros) é:

**Administrar itens de fornecedor**
- Empresa: `4690`
- Status: `Itens compensados`
- Tipo de item: `3 itens`
- Moeda da transação: `BRL`
- **Data de compensação: a data do pagamento** (ex.: `19.08.2026`)
- **Atribuição: `<vazio>` + a data no formato DDMMAAAA** (ex.: `19082026`)

Os dois últimos são os que importam, e cada um resolve um problema real:

- Filtrar por **Data de compensação** (e NÃO por `Dt.lançamento`) traz a
  fatura mesmo que ela tenha sido lançada dias antes do pagamento. Filtrando
  por data de lançamento, a fatura 5015282 (CAIXA, lançada em 17/08 e paga em
  19/08) sumia, e o pagamento voltava pro produto errado.
- Incluir **`<vazio>` na Atribuição** cobre lançamento com esse campo
  preenchido em formato invertido. O doc 1300006133 (-93.551,92) veio com
  `20260819` em vez de `19082026`; sem o `<vazio>` a fatura dele não saía no
  export e a maior linha da Folha ficava sem confirmação de texto.

Com esses filtros o export saiu com 482 linhas e a aba Validações fechou com
"Folha/PIX confirmados por texto de item: OK" — ou seja, todo Folha e PIX
confirmado por código do fornecedor + mensagem no texto, sem palpite.

**Partidas individuais no Razão**: mesma janela de pagamento; é dele que sai a
linha bancária (KZ) que define o valor de cada documento — exceto Folha de
Pagamento e PIX, cujo valor vem da soma das faturas (ver "Valor de Folha de
Pagamento e PIX" mais abaixo).

Se algum dia o export vier incompleto, o relatório continua saindo com os
valores certos (a linha bancária vem do outro arquivo), mas a aba Validações
acusa ALERTA apontando quais documentos foram classificados só pelo código do
fornecedor — é o sinal de que os filtros precisam ser revistos.

## Tratamento de erro na interface

Quando `gerar_base.py` falha por um motivo já conhecido (ex.: o arquivo
selecionado não tem a aba "Exportação SAPUI5" — não é o export certo do
SAP), o painel de erro da interface mostra só a mensagem clara, não o
traceback inteiro do Python. O traceback completo continua indo pro console
(que abre automaticamente quando dá erro), pra quem precisar depurar mais a
fundo.

## Valor de Folha de Pagamento e PIX

O `Valor` desses dois produtos vem da **soma das faturas do documento** —
coluna `Montante (ME)` do export "Partidas individuais no Razão", somando
todas as linhas com aquele `Lançto.compensação` — e não do líquido da linha
de baixa bancária (`Mont.moeda empresa`). São exatamente os dois produtos
que o SAP identifica pelo `Texto de item`, e o montante que vai pra
aprovação é o das faturas: a baixa bancária pode vir compensada com outros
lançamentos do mesmo dia e sair diferente do que o portal do banco mostra
pra aprovar.

`TM5` e `Pagamento Fornecedores` continuam com o valor da linha bancária —
neles o líquido da baixa é o próprio pagamento.

Detalhes do comportamento:

- A linha de pagamento (a que se compensa a si mesma, `Lançamento contábil`
  = `Lançto.compensação`) fica de fora da soma; ela é a contrapartida das
  faturas e zeraria o total.
- O sinal da linha bancária é preservado (saída de caixa continua
  negativa), já que `Montante (ME)` vem com a convenção invertida do razão
  de fornecedor.
- Documento sem fatura no export — ou export reduzido, sem a coluna
  `Montante (ME)` — mantém o valor bancário, que é o único dado
  disponível. O check "Folha/PIX confirmados por texto de item" já sinaliza
  esse caso.
- A aba `Validações` traz o check **"Valor de Folha/PIX pela soma das
  faturas"**: `OK` quando os dois números batem, `ALERTA` listando
  documento, valor do banco e valor das faturas quando o ajuste mudou
  algum valor.
- Isso **não** divide documento entre produtos — cada documento continua
  inteiro num produto só; só muda de onde sai o valor.

## Referência circular no `.xlsx` gerado

Se um produto (Folha de Pagamento, PIX, Pagamento Fornecedores ou TM5) ficar
com **zero documentos** naquela rodada, a aba dele grava o total como `0`
fixo, em vez de uma fórmula `SUM` sobre um intervalo vazio — um intervalo
assim (ex.: `B5:B4`) o Excel normaliza incluindo a própria célula do total,
o que dispara o aviso "Existe uma ou mais referências circulares" ao abrir o
arquivo. Corrigido; abas com dados continuam usando fórmula normalmente.

## Observações sobre `config.py`

`DATA_REFERENCIA`, `ARQUIVO_BASE` e `OVERRIDES_SEMANA` (em `config.py` e no
topo de `gerar_base.py`) continuam sendo os parâmetros editados manualmente
toda semana, exatamente como antes — o app não modifica isso automaticamente.
Se algum lançamento precisar de exceção manual (PIX sem padrão detectável,
duplicidade etc.), edite `OVERRIDES_SEMANA` em `python/gerar_base.py` antes
de gerar o relatório daquela semana.

O nome/pasta do arquivo gerado (`Payments_<data>.xlsx`) é baseado na data
real encontrada nos lançamentos analisados (`Posting Date`), não em
`config.DATA_REFERENCIA` — assim ele não sai com a data errada se alguém
esquecer de atualizar `DATA_REFERENCIA` na semana certa. O conteúdo do
relatório (cabeçalho da aba Resumo, check "Posting Date == Data_Referencia"
na aba Validações) continua comparando contra `config.DATA_REFERENCIA` como
antes — se as datas não baterem, isso aparece como BLOQUEIO na aba
Validações.
