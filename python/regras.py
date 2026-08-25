"""Regras de classificação de produto, em ordem de precedência.

Fonte única de dados: relatório SAP "Administrar itens de fornecedor"
(a mesma linha de baixa bancária ZP/KZ), filtrado nas contas de banco
1001002000 (Santander) e 1000000050 (BB, quando o e-mail abranger os dois).

STATUS DE ANCORAGEM
--------------------
R0 (SA -> excluído)     : verificada. Documento de conta-Razão (imposto de
                          importação), fora do escopo de pagamento.
R1 (ZP -> TM5)          : VERIFICADA contra a base de 29.07.2026
                          (248/248, sem falso positivo).
R6 (flag manual -> PIX) : não é regra dedutível — é exceção operacional.
                          Um documento entra aqui quando alguém pagou via
                          PIX manualmente naquela semana (ex.: 29.07.2026,
                          doc 1300005654, BESSA SERVICOS DE APOIO
                          ADMINISTRAT LTDA, -R$2.415,00). Mantido em
                          `flags_pix`, passado por fora a cada rodada.
R4 (ICBRWA -> Folha)    : APROXIMADA, com limite conhecido. O relatório
                          "Administrar itens de fornecedor" não carrega a
                          conta G/L de despesa (2511110100, 2514210000 etc.)
                          nem o centro de lucro 46901101 do mapa de Folha —
                          esses campos só existem no documento KR da fatura,
                          não na linha de baixa bancária. Nesta fonte, TODO
                          lançamento com fornecedor ICBRWA é tratado como
                          Folha, sem diferenciar de um ICBRWA não-Folha.
                          Na base de 29.07.2026 isso superestimou Folha em
                          R$52.648,40 (~1,7% do total). Pra eliminar esse
                          erro seria preciso um segundo relatório (partidas
                          de fornecedor/FBL1N da fatura KR) cruzado por
                          Lançto.compensação — hoje fora de escopo por
                          decisão de praticidade.
R5 (Caixa -> PIX/FGTS)  : VERIFICADA contra a base aprovada de 12.08.2026.
                          CAIXA ECONOMICA FEDERAL (102087) pagando FGTS vai
                          pro produto PIX. Confirmado: doc 1300006090, cujas
                          4 faturas têm "Texto de item" = "PIX" e referência
                          "GFD/GDF 08.2026" (Guia FGTS Digital). Os docs
                          1300006071 e 1300006088 (par de estorno, somam
                          zero) não têm linha de fatura no export e caem
                          aqui pelo padrão — igual à planilha aprovada.

R5b (Caixa que NÃO é     : VERIFICADA contra os extratos de 19.08.2026.
     FGTS -> Fornecedor)   Caixa nem sempre é FGTS. Quando a fatura TEM
                          "Texto de item" e ele não é o marcador "PIX", o
                          pagamento não é FGTS e sai pelo convênio PAGTO
                          FORNECEDORES. Prova: doc 1300006169 (-8.558,51),
                          fatura 5015282, texto "RT 0000023-40.2025.5.09.0665
                          - MARCOS ANTONIO OKON" — depósito de reclamatória
                          trabalhista, não FGTS. Com ele em Fornecedores o
                          convênio fecha exato em R$91.377,50 (46.854,94 +
                          5.597,22 + 34.613,25 + 4.312,09) e a semana fica
                          sem nenhum PIX, igual ao banco.

                          Guarda proposital "só quando existe texto": sem
                          texto não dá pra afirmar que não é FGTS, então
                          mantém o padrão R5 (PIX). É o que preserva os docs
                          1300006071/1300006088 de 12.08.2026, que não têm
                          fatura no export e estão como PIX no aprovado.

R3 vs R4 (ICBRWA)       : VERIFICADA contra a base aprovada de 12.08.2026.
                          O campo "Texto de item" = "PIX" NÃO vale pra
                          fornecedor ICBRWA (NORDEX ENERGY BRASIL): mesmo
                          marcado como PIX, lançamento de ICBRWA é sempre
                          Folha de Pagamento (ou Pagamento Fornecedores via
                          regra PEN), nunca PIX. Confirmado: docs 1300006091
                          (-115.516,12) e 1300006092 (-8.815,55) vieram com
                          "Texto de item" = "PIX" no export, mas na planilha
                          aprovada estão como Folha de Pagamento. Por isso
                          R3 exclui explicitamente ICBRWA. Para os demais
                          fornecedores o marcador continua valendo (ex.: doc
                          1300006094, TRIBUNAL REGIONAL TRABALHO 5A REGIÃO,
                          -548,26 -> PIX).

R2b (ICBRWA rescisão)   : VERIFICADA contra os extratos do Santander de
                          19.08.2026. Nem todo ICBRWA é Folha: rescisão e
                          pensão saem por TED "outra titularidade", dentro
                          do convênio PAGTO FORNECEDORES, não do convênio
                          FOLHA DE PAGAMENTO. Prova: a linha "INCLUIR TED
                          CIP OUTRA TITULARIDADE" do banco (R$4.312,09 em 2
                          lançamentos) é exatamente doc 1300006175
                          ("Rescisão Compl - 08/2026", -2.604,08) + doc
                          1300006176 ("Folha de Pagto - Pensão", -1.708,01);
                          e o convênio de Folha (R$152.133,20) é exatamente
                          os outros três: 1300006133 (-93.551,92),
                          1300006134 (-31.872,42) e 1300006177 (-26.708,86).
                          Pensão já caía certo pela R2 (referência PEN);
                          rescisão não tinha marcador e caía em Folha.
                          Por isso R2b manda "Texto de item" com "RESCIS"
                          (ICBRWA) para Pagamento Fornecedores.

                          Desenho proposital — lista de EXCLUSÃO, não de
                          inclusão: só tira de Folha o que é comprovadamente
                          rescisão/pensão. Um whitelist ("só é Folha se o
                          texto disser salário/folha/adiantamento") quebraria
                          o doc 1300006133, que não tem linha de fatura no
                          export e portanto não tem "Texto de item" nenhum —
                          ele depende de continuar caindo no padrão R4.

NAO AUTOMATIZAR         : na planilha aprovada de 12.08.2026 o doc
                          1300006091 (-115.516,12) aparece dividido em duas
                          linhas: Folha (-104.193,13) + Pagamento
                          Fornecedores (-11.322,99). Isso foi encaixe MANUAL
                          pontual do aprovador, não regra. Confirmado com o
                          usuário em 19.08.2026. Os dois valores não existem
                          em nenhum dos dois relatórios SAP — não há como
                          deduzir a quebra, e não se deve tentar. O script
                          classifica o documento inteiro num produto só;
                          se precisar dividir de novo, é ajuste manual na
                          planilha depois de gerada.

HISTORICO DO MARCADOR   : confirmado pelo usuário em 19.08.2026 — o
                          preenchimento do "Texto de item" com a informação
                          de PIX / Folha de pagamento passou a ser feito
                          AGORA; nas semanas antigas esse campo não trazia
                          essa informação. Consequência prática:

                          - bases antigas (até ~05.08.2026) dependem mais do
                            padrão por código de fornecedor (R4/R5), porque
                            simplesmente não há texto pra conferir;
                          - bases novas tendem a ter o texto sempre que a
                            linha de fatura vier no export, então o alerta
                            "Folha/PIX confirmados por texto de item" deve
                            ficar cada vez mais raro.

                          O que NÃO se resolve sozinho com o tempo é a linha
                          de fatura faltando no export (ex.: doc 1300006133,
                          -93.551,92, cuja fatura 5015173 existe no SAP com
                          texto "Folha de Pagamento F01190826..." mas não sai
                          no relatório). Enquanto isso ocorrer, o padrão por
                          código de fornecedor precisa continuar existindo —
                          torná-lo obrigatório erraria R$93 mil nessa semana.

Antes de usar `classificar()` em produção, MODO_CLASSIFICACAO precisa
estar True — ligar só depois de confirmar CAMPOS_BRUTOS contra o export
real da semana.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

MODO_CLASSIFICACAO: bool = True

TM5 = "TM5"
FOLHA = "Folha de Pagamento"
PIX = "PIX"
FORNECEDORES = "Pagamento Fornecedores"
EXCLUIDO = "__EXCLUIDO__"

# Nomes de campo reais no export "Administrar itens de fornecedor"
# (aba "Exportação SAPUI5"). Conferir a cada semana se o SAP não mudou.
CAMPOS_BRUTOS: dict[str, str] = {
    "documento": "Lançamento contábil",
    "tipo_lancamento": "Tipo lçto.contábil",
    "contrapartida": "Cta.contrapartida",
    "conta_razao": "Conta do Razão",
    "valor": "Mont.moeda empresa",
    "data": "Data de lançamento",
}

# Contas de banco válidas. Filtrar por elas ANTES de classificar —
# qualquer outra Conta do Razão é fora do escopo deste fluxo.
CONTAS_BANCO: frozenset[str] = frozenset({"1001002000", "1000000050"})

PREFIXO_ZP = "ZP"
PREFIXO_SA = "SA"
FORNECEDOR_ICBRWA = "ICBRWA"
FORNECEDOR_CAIXA = "102087"
TOKEN_PEN = "PEN"
# Prefixo sem acento de propósito: pega "Rescisão", "Rescisao", "Rescisões".
TOKEN_RESCISAO = "RESCIS"
# Se o texto já diz "Folha", a rescisão É paga pelo convênio de Folha (ver R2b).
TOKEN_FOLHA = "FOLHA"


@dataclass(frozen=True)
class Regra:
    """Uma regra da cadeia. `teste` recebe a linha e devolve True se aplica."""

    ordem: int
    nome: str
    produto: str
    teste: Callable[[pd.Series], bool]
    ancorada: bool


def _txt(linha: pd.Series, campo: str) -> str:
    return str(linha.get(CAMPOS_BRUTOS[campo], "") or "").strip().upper()


def conta_banco_valida(valor_conta_razao: object) -> bool:
    """Conta do Razão vem como '1001002000 (BANCOS ...)' — comparar só o código."""
    return str(valor_conta_razao or "").split()[:1] and str(valor_conta_razao).split()[0] in CONTAS_BANCO


def doc_str(valor: object) -> str:
    """Normaliza número de documento — pandas às vezes lê como float
    (123.0) em vez de int/str. Sempre comparar pela forma sem '.0'."""
    texto = str(valor or "").strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def _r0_sa(linha: pd.Series) -> bool:
    """SA e ST são os dois tipos observados de 'Documento cta.Razão' —
    lançamento técnico de conta-Razão (imposto de importação, reconciliação
    bancária), nunca um pagamento de verdade. Confirmado na semana de
    15.07.2026: um lançamento ST resolveu pra 'Reconciliação Bancária' em
    vez de fornecedor real e duplicava um pagamento já contado em TM5."""
    tipo = _txt(linha, "tipo_lancamento")
    return tipo.startswith(PREFIXO_SA) or tipo.startswith("ST")


def _r1_zp(linha: pd.Series) -> bool:
    return _txt(linha, "tipo_lancamento").startswith(PREFIXO_ZP)


def _r4_icbrwa(linha: pd.Series) -> bool:
    return FORNECEDOR_ICBRWA in _txt(linha, "contrapartida")


def _r5_caixa(linha: pd.Series) -> bool:
    return FORNECEDOR_CAIXA in _txt(linha, "contrapartida")


CADEIA: tuple[Regra, ...] = (
    Regra(0, "SA — imposto de importação, fora do escopo", EXCLUIDO, _r0_sa, True),
    Regra(1, "ZP — lançamento de pagamento", TM5, _r1_zp, True),
    # R6 (exceção manual) e R2 (PEN) são checadas à parte, antes desta
    # cadeia — ver classificar().
    Regra(4, "ICBRWA — Folha", FOLHA, _r4_icbrwa, False),
    Regra(5, "Caixa Econômica — FGTS", PIX, _r5_caixa, False),
    # Fallback é aplicado após a cadeia.
)

FALLBACK = FORNECEDORES

# Nomes de campo reais no export "Partidas individuais no Razão"
# (aba "Exportação SAPUI5", 22 colunas). Usado só pra achar a referência
# da fatura de cada lançamento ICBRWA, via join por Lançto.compensação.
CAMPOS_PARTIDAS: dict[str, str] = {
    "documento_fatura": "Lançamento contábil",
    "fornecedor": "Fornecedor",
    "referencia": "Referência",
    "lancto_compensacao": "Lançto.compensação",
    "texto_item": "Texto de item",
}

TOKEN_PIX_TEXTO_ITEM = "PIX"


def _e_linha_de_pagamento(linha: pd.Series) -> bool:
    """True quando a linha é a própria baixa (KZ/ZP) e não a fatura (KR).

    Depende da variante do export: quando o filtro de Atribuição é removido,
    o SAP passa a trazer, além da fatura, a linha de pagamento que a compensa
    — as duas com o mesmo Lançto.compensação. A linha de pagamento se compensa
    a si mesma (Lançamento contábil == Lançto.compensação) e traz sempre o
    texto genérico "Pagamento fornecedor <nome>", que não serve pra
    classificar; se ela sobrescrever o texto da fatura, marcadores como
    "Rescisão"/"PIX" se perdem e o lançamento cai no padrão errado.
    Confirmado em 19.08.2026 com a variante V2: a rescisão do doc 1300006175
    voltou pra Folha porque o texto virou "Pagamento fornecedor NORDEX...".
    """
    doc = doc_str(linha.get(CAMPOS_PARTIDAS["documento_fatura"], ""))
    comp = doc_str(linha.get(CAMPOS_PARTIDAS["lancto_compensacao"], ""))
    return bool(doc) and doc == comp


def textos_item_por_documento(df_partidas: pd.DataFrame) -> dict[str, str]:
    """Junta o relatório 'Partidas individuais no Razão' pra achar, pra
    cada documento de PAGAMENTO (Lançto.compensação), o texto do campo
    'Texto de item' da fatura que originou aquele pagamento — de QUALQUER
    fornecedor, não só ICBRWA.

    Usado pela regra R3 (Texto de item = 'PIX' -> PIX). Confirmado em
    05.08.2026: doc 1300005888 (fatura 5014356, TRIBUNAL REGIONAL
    TRABALHO 5A REGIÃO) veio com 'Texto de item' = 'PIX' — diferente do
    padrão normal do campo ('Fatura - bruto <fornecedor>' / 'Fatura do
    fornecedor <fornecedor>'), então é um marcador deliberado, não uma
    coincidência de texto do nome do fornecedor.
    """
    doc_fatura = CAMPOS_PARTIDAS["documento_fatura"]
    comp = CAMPOS_PARTIDAS["lancto_compensacao"]
    texto = CAMPOS_PARTIDAS["texto_item"]

    out: dict[str, str] = {}
    for _, linha in df_partidas.iterrows():
        if _e_linha_de_pagamento(linha):
            continue
        doc_pagamento = doc_str(linha.get(comp, ""))
        t = str(linha.get(texto, "") or "")
        if doc_pagamento and doc_pagamento != "None" and t:
            out[doc_pagamento] = t
    return out


def referencias_fatura_icbrwa(df_partidas: pd.DataFrame) -> dict[str, str]:
    """Junta o relatório 'Partidas individuais no Razão' pra achar,
    pra cada documento de PAGAMENTO (Lançto.compensação), a referência da
    fatura (Referência) do fornecedor ICBRWA que originou aquele pagamento.

    Usado pela regra R2 (referência com 'PEN' -> Pagamento Fornecedores).
    """
    doc_fatura = CAMPOS_PARTIDAS["documento_fatura"]
    fornecedor = CAMPOS_PARTIDAS["fornecedor"]
    referencia = CAMPOS_PARTIDAS["referencia"]
    comp = CAMPOS_PARTIDAS["lancto_compensacao"]

    icbrwa = df_partidas[df_partidas[fornecedor].astype(str) == FORNECEDOR_ICBRWA]
    out: dict[str, str] = {}
    for _, linha in icbrwa.iterrows():
        if _e_linha_de_pagamento(linha):
            continue
        doc_pagamento = doc_str(linha.get(comp, ""))
        ref = str(linha.get(referencia, "") or "")
        if doc_pagamento and doc_pagamento != "None" and ref and ref != "nan":
            out[doc_pagamento] = ref
    return out


def _marcar_reversoes(base: pd.DataFrame) -> pd.Series:
    """Marca lançamentos ZP positivos que são reversão de um pagamento ZP
    negativo já existente (mesmo fornecedor/Cta.contrapartida, mesmo valor
    absoluto). Mantém o negativo (o pagamento real), exclui o positivo —
    não soma os dois como se fossem zero, porque isso faz o pagamento real
    desaparecer do relatório. Confirmado na semana de 15.07.2026 contra o
    e-mail de aprovação: ITS TELECOMUNICACOES e TELEFONICA BRASIL SA cada
    uma tinha um par assim, e a soma "líquida zero" tirava R$35.725,98 do
    TM5 que deveriam estar lá.
    """
    tipo = base[CAMPOS_BRUTOS["tipo_lancamento"]].astype(str)
    valor = base[CAMPOS_BRUTOS["valor"]]
    contraparte = base[CAMPOS_BRUTOS["contrapartida"]].astype(str)
    zp = tipo.str.upper().str.startswith(PREFIXO_ZP)

    chave = contraparte.where(zp) + "|" + valor.abs().round(2).astype(str).where(zp)
    grupos = chave[zp].value_counts()
    pares = set(grupos[grupos >= 2].index)

    excluir = pd.Series(False, index=base.index)
    for k in pares:
        idx_grupo = chave[chave == k].index
        vals = valor.loc[idx_grupo]
        if (vals > 0).any() and (vals < 0).any():
            excluir.loc[idx_grupo[vals > 0]] = True
    return excluir


def classificar(
    df: pd.DataFrame,
    overrides: dict[str, str] | None = None,
    referencias_fatura: dict[str, str] | None = None,
    textos_item: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Filtra pelas contas de banco e aplica a cadeia.

    Devolve o df com colunas `Produto` e `RegraAplicada`, já sem as linhas
    fora das contas de banco e sem os documentos SA (excluídos).

    `textos_item` é o resultado de `textos_item_por_documento()` —
    {documento_pagamento: texto_de_item}. A partir de 05.08.2026 o SAP
    passou a marcar pagamentos feitos via PIX diretamente no campo "Texto
    de item" da fatura (valor exatamente "PIX", em vez do padrão normal
    "Fatura - bruto <fornecedor>"). Quando isso acontece, classifica como
    PIX automaticamente — não precisa mais cair no `overrides` manual.
    Continua funcionando pra qualquer fornecedor, não só ICBRWA (o
    exemplo confirmado foi TRIBUNAL REGIONAL TRABALHO 5A REGIÃO,
    doc 1300005888, -R$3.001,33).

    `referencias_fatura` é o resultado de `referencias_fatura_icbrwa()` —
    {documento_pagamento: referência_fatura}. Sempre que um lançamento
    ICBRWA tiver referência contendo "PEN" (Pensão Alimentícia, e também
    estornos/correções — ex.: PENFER), ele conta como Pagamento
    Fornecedores em vez de Folha. Confirmado contra a base de 29.07.2026:
    "01PEN10002" bateu exato com a Relação de Pensão Alimentícia mensal
    (R$45.635,61) e "PENFER10290726" era um estorno já resolvido.

    `overrides` é um dict {documento: produto} pro que sobra sem padrão
    detectável — continua existindo mesmo com a regra de Texto de item
    acima, porque nem toda semana o SAP vai marcar 100% dos PIX assim
    (o modelo é novo a partir de 05.08.2026), e porque cobre outros casos
    sem padrão. Aceita qualquer produto válido, ou `regras.EXCLUIDO`
    quando o documento é uma duplicidade/erro de lançamento que não
    deveria contar de jeito nenhum (ex.: doc 1300005522, 15.07.2026 —
    duplicava um pagamento da ITS TELECOMUNICACOES já contado em TM5 via
    KZ em vez de ZP; não pega na regra de reversão porque tem tipo
    diferente do original). Casos conhecidos que continuam manuais:
      - PIX avulso, fora do fluxo normal, ANTES de 05.08.2026 ou em
        semana sem o novo marcador (ex.: doc 1300005654, 29.07.2026,
        BESSA SERVICOS — pagamento manual via PIX)
      - Folha paga via PIX por sigilo (ex.: doc 1300005682/fatura 5013945,
        29.07.2026, -R$4.777,88 — confirmado batendo com a Folha Mensal:
        Estabelecimento 8 R$3.692,87 + Estabelecimento 17 R$1.085,01).
        Referência "F29072026" não tem "PEN", não cai na regra automática.
    """
    if not MODO_CLASSIFICACAO:
        raise RuntimeError(
            "MODO_CLASSIFICACAO=False. Confirmar CAMPOS_BRUTOS contra o export "
            "real da semana antes de habilitar."
        )

    overrides = overrides or {}
    referencias_fatura = referencias_fatura or {}
    textos_item = textos_item or {}
    conta_razao = CAMPOS_BRUTOS["conta_razao"]
    doc = CAMPOS_BRUTOS["documento"]

    base = df[df[conta_razao].apply(conta_banco_valida)].copy()
    excluir_reversao = _marcar_reversoes(base)

    produto = pd.Series(pd.NA, index=base.index, dtype="object")
    regra = pd.Series(pd.NA, index=base.index, dtype="object")

    for i, linha in base.iterrows():
        documento = doc_str(linha.get(doc, ""))

        if excluir_reversao.loc[i]:
            produto.loc[i] = EXCLUIDO
            regra.loc[i] = "R0b — reversão de pagamento (mantido só o original)"
            continue

        if documento in overrides:
            produto.loc[i] = overrides[documento]
            regra.loc[i] = f"R6 — exceção manual ({documento})"
            continue

        texto = textos_item.get(documento, "")
        if texto.strip().upper() == TOKEN_PIX_TEXTO_ITEM and not _r4_icbrwa(linha):
            produto.loc[i] = PIX
            regra.loc[i] = f"R3 — Texto de item = PIX ({documento})"
            continue

        ref = referencias_fatura.get(documento, "")
        if TOKEN_PEN in ref.upper():
            produto.loc[i] = FORNECEDORES
            regra.loc[i] = f"R2 — ICBRWA com referência PEN ({ref})"
            continue

        if _r4_icbrwa(linha) and TOKEN_RESCISAO in texto.upper() and TOKEN_FOLHA not in texto.upper():
            produto.loc[i] = FORNECEDORES
            regra.loc[i] = f"R2b — ICBRWA rescisão, pago por TED ({documento})"
            continue

        # R5b — Caixa Econômica NEM SEMPRE é FGTS/PIX. Quando a fatura traz
        # "Texto de item" e ele NÃO é o marcador "PIX", o pagamento não é
        # FGTS (ex.: depósito de reclamatória trabalhista "RT ..."), e sai
        # pelo convênio de fornecedores. Só vale quando existe texto: sem
        # texto não dá pra afirmar nada, então cai no padrão R5 (PIX).
        if _r5_caixa(linha) and texto.strip() and texto.strip().upper() != TOKEN_PIX_TEXTO_ITEM:
            produto.loc[i] = FORNECEDORES
            regra.loc[i] = f"R5b — Caixa sem marcador PIX no texto de item ({documento})"
            continue

        for r in CADEIA:
            if r.teste(linha):
                produto.loc[i], regra.loc[i] = r.produto, f"R{r.ordem} — {r.nome}"
                break
        else:
            produto.loc[i], regra.loc[i] = FALLBACK, "R7 — fallback"

    out = base.assign(Produto=produto, RegraAplicada=regra)
    return out[out["Produto"] != EXCLUIDO].copy()


def conferir_zp(df: pd.DataFrame, col_tipo: str, col_produto: str) -> list[str]:
    """R1 é a única regra reproduzível a partir da base já classificada.

    Devolve lista de inconsistências (vazia = coerente).
    """
    erros: list[str] = []
    tipo = df[col_tipo].astype(str).str.upper()
    zp = tipo.str.startswith(PREFIXO_ZP)

    fora = df.loc[zp & (df[col_produto] != TM5), col_produto]
    if len(fora):
        erros.append(f"{len(fora)} lançamento(s) ZP fora de TM5: {sorted(set(fora))}")

    invasor = df.loc[~zp & (df[col_produto] == TM5)]
    if len(invasor):
        erros.append(f"{len(invasor)} lançamento(s) TM5 sem tipo ZP")

    return erros
