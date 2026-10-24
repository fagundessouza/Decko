"""Módulo núcleo: empresas, usuários, autenticação, RBAC e auditoria.

O carregador de módulos procura o atributo ``router`` neste pacote.
Importar ``models`` aqui garante que as tabelas estejam registradas no metadata antes de
o Alembic comparar o schema.

Importar ``activation`` registra, no host, a verificação de módulo ativo por empresa. Isso
acontece na importação porque o host aplica a verificação ao montar os routers, e o núcleo
é sempre carregado primeiro — ver ``docs/adr/0004-ativacao-de-modulo-por-empresa.md``.
"""

from decko_modules.core import activation as activation
from decko_modules.core import models as models
from decko_modules.core.router import router as router

__all__ = ["activation", "models", "router"]
