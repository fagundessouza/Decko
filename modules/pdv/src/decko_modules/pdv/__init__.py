"""Ponto de venda: venda de balcão em cima da base comercial.

Não tem cadastro de produto nem estoque próprios — usa os do módulo ``comercial``, que
declara em ``depends``. Ver ``docs/adr/0008-ponto-de-venda.md``.
"""

from decko_modules.pdv import models as models
from decko_modules.pdv.router import router as router

__all__ = ["models", "router"]
