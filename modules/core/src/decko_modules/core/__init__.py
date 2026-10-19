"""Módulo núcleo: empresas, usuários, autenticação, RBAC e auditoria.

O carregador de módulos procura o atributo ``router`` neste pacote.
Importar ``models`` aqui garante que as tabelas estejam registradas no metadata antes de
o Alembic comparar o schema.
"""

from decko_modules.core import models as models
from decko_modules.core.router import router as router

__all__ = ["models", "router"]
