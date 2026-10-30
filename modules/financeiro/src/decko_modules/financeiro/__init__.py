"""Conta de recebimento: para onde o dinheiro foi.

O ponto de venda diz como o cliente pagou; este módulo diz onde caiu.

Decisões em ``docs/adr/0014-conta-de-recebimento.md``.
"""

from decko_modules.financeiro import models as models
from decko_modules.financeiro.router import router as router

__all__ = ["models", "router"]
