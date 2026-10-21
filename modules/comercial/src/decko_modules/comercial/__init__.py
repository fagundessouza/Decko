"""Base comercial: unidade, categoria, produto, lote, preço e razão de estoque.

É o que ferragista, supermercado, lanchonete e distribuidora usam igual. As verticais
dependem deste módulo; ele não depende de nenhuma.

Decisões em ``docs/adr/0006-base-comercial.md``.
"""

from decko_modules.comercial import models as models
from decko_modules.comercial.router import router as router

__all__ = ["models", "router"]
