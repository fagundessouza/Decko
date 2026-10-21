"""Módulo de pulverização agrícola: operações de voo e relatórios exigidos pelo MAPA.

Requisitos em ``docs/discovery/agro-planejamento-operacional.md``, derivados do formulário
em uso na operação, não de suposição.
"""

from decko_modules.agro import models as models
from decko_modules.agro.router import router as router

__all__ = ["models", "router"]
