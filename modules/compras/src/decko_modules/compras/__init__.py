"""Compras: a nota do fornecedor vira produto cadastrado e estoque lançado.

Decisões em ``docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md``.
"""

from decko_modules.compras import models as models
from decko_modules.compras.router import router as router

__all__ = ["models", "router"]
