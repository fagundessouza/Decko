"""Clientes: quem compra da empresa.

Dado pessoal, então criptografia de transporte, RBAC e trilha de auditoria entram junto
com a funcionalidade — ver regra 2 do ``CLAUDE.md``.
"""

from decko_modules.clientes import models as models
from decko_modules.clientes.router import router as router

__all__ = ["models", "router"]
