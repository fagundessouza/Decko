"""Consumo interno de estoque, com centro de custo.

O que saiu do estoque sem ser venda, lançado contra um centro — e o custo somado de cada
um, juntando consumo e despesa.

Decisões em ``docs/adr/0026-consumo-interno-e-custo-por-centro.md``.
"""

from decko_modules.custos import models as models
from decko_modules.custos.router import router as router

__all__ = ["models", "router"]
