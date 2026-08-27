"""Parâmetros da execução semanal.

Editar SOMENTE o bloco JANELA a cada semana. O resto é estrutural.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

# ============================================================
# JANELA — editar toda semana
# ============================================================

DATA_REFERENCIA: date = date(2026, 8, 26)

ARQUIVO_BASE: str = "Payments 29.07.2026.xlsx"
ABA_BASE: str = "SAP"

# ============================================================
# ESTRUTURAL — só muda se o export SAP mudar de layout
# ============================================================

DIR_ENTRADA = Path("entrada")
DIR_SAIDA = Path("saida")

EMPRESA = "4690 (Nordex Energy Brasil LTDA)"
CONTA_GL = "1001002000 (BANCOS CONTA MOVIMENTO - SAÍDA)"
STATUS_ESPERADO = "Pendentes"
BANCO = "Santander"

PRODUTOS: tuple[str, ...] = (
    "Folha de Pagamento",
    "PIX",
    "Pagamento Fornecedores",
    "TM5",
)

# Mapeamento por POSIÇÃO de coluna (0-based) na aba SAP.
# O export traz cabeçalhos deslocados em relação ao conteúdo:
# "Business Transaction Type" carrega o nº do documento,
# "Journal Entry Type" carrega data. Não mapear por nome.
COLUNAS: dict[str, int] = {
    "Documento": 4,
    "TipoLancamento": 5,
    "Fornecedor": 7,
    "Produto": 8,
    "Status": 9,
    "Data": 12,
    "Valor": 14,
    "Empresa": 0,
    "ContaGL": 1,
}

# Documento acima deste valor absoluto entra no log de atenção.
LIMITE_ATENCAO: float = 500_000.00


@dataclass(frozen=True)
class Janela:
    """Snapshot imutável dos parâmetros da semana."""

    data_referencia: date
    arquivo_base: Path
    aba: str

    @property
    def rotulo(self) -> str:
        return self.data_referencia.strftime("%d.%m.%Y")

    @property
    def slug(self) -> str:
        return self.data_referencia.strftime("%Y-%m-%d")


def janela_atual() -> Janela:
    return Janela(
        data_referencia=DATA_REFERENCIA,
        arquivo_base=DIR_ENTRADA / ARQUIVO_BASE,
        aba=ABA_BASE,
    )
