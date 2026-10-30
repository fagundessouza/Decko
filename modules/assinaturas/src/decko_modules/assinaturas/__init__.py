"""Assinatura recorrente: plano, assinante e a cobrança de cada mês.

O primeiro cliente deste módulo é a própria Decko, que passou a vender por assinatura —
ver ``docs/NEGOCIO.md``, seção 1.

Decisões em ``docs/adr/0013-assinatura-recorrente.md``.
"""

from decko_modules.assinaturas import models as models
from decko_modules.assinaturas.router import router as router

__all__ = ["models", "router"]
