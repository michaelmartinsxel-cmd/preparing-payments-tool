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

`build_exe.bat` procura sozinho uma instalação WinPython (`WPy64-*`) na área
de trabalho/pasta do usuário e usa o `python.exe`/`pip` de dentro dela — não
precisa abrir o "WinPython Command Prompt" na mão antes. Se não achar
nenhuma e `python` também não estiver no PATH, ele avisa e para (nesse caso
aí sim: abra o WinPython Command Prompt, `cd /d` até esta pasta, e rode
`build_exe.bat` de lá).

O `.exe` costuma sair grande (150–250 MB) porque leva o Python inteiro +
pandas/numpy dentro — normal para esse tipo de empacotamento, não é bug.

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
linha bancária (KZ) que define o valor de cada documento.

Se algum dia o export vier incompleto, o relatório continua saindo com os
valores certos (a linha bancária vem do outro arquivo), mas a aba Validações
acusa ALERTA apontando quais documentos foram classificados só pelo código do
fornecedor — é o sinal de que os filtros precisam ser revistos.

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
