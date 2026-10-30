"""Porta de ativação de módulo por empresa.

Quem monta as rotas é o host, e é aqui que a verificação precisa estar para que nenhum
módulo consiga ficar desprotegido por esquecimento. Mas o host não pode importar um módulo
(``docs/ARCHITECTURE.md`` §2), e quem sabe quem está autenticado — e conhece a tabela de
empresas — é o ``core``.

A saída é inverter: o host define a porta, o ``core`` registra a implementação ao ser
importado, e o host aplica o resultado na montagem sem conhecer o schema de ninguém.

Registra-se a dependência pronta, e não apenas uma consulta, porque a verificação precisa
do tenant autenticado: montá-la exige a cadeia de autenticação, que pertence ao ``core``.

Decisão e alternativas descartadas: ``docs/adr/0004-ativacao-de-modulo-por-empresa.md``.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

# Recebe o nome do módulo e devolve uma dependência do FastAPI que recusa a requisição
# quando aquele módulo não está ativo na empresa autenticada.
ActivationGuardFactory = Callable[[str], Any]

_factory: ActivationGuardFactory | None = None


class ActivationNotConfiguredError(RuntimeError):
    """Nenhum módulo registrou a verificação de ativação."""


def register_activation_guard(factory: ActivationGuardFactory) -> None:
    """Registra a fábrica de verificação. Chamada pelo ``core`` ao ser importado."""
    global _factory
    _factory = factory


def activation_guard_for(module_name: str) -> Any:
    """Devolve a dependência que protege as rotas daquele módulo.

    Levanta erro quando nada foi registrado, em vez de montar rota sem proteção: deixar
    passar é a falha errada de se ter aqui, e falhar na inicialização é melhor que
    descobrir em produção que um módulo ficou aberto.
    """
    if _factory is None:
        raise ActivationNotConfiguredError(
            f"Módulo '{module_name}' não pode ser montado: nenhuma verificação de "
            "ativação foi registrada. O módulo núcleo foi carregado antes dele?"
        )
    return _factory(module_name)


# ---------------------------------------------------------------- permissões

# Recebe {nome do módulo: permissões que ele declara} e acerta os papéis das empresas que
# têm aquele módulo ativo. Devolve quantas permissões concedeu.
PermissionReconciler = Callable[[Mapping[str, Sequence[str]]], Awaitable[int]]

_reconciler: PermissionReconciler | None = None


def register_permission_reconciler(reconciler: PermissionReconciler) -> None:
    """Registra quem sabe acertar permissão. Chamada pelo ``core`` ao ser importado."""
    global _reconciler
    _reconciler = reconciler


async def reconcile_permissions(declared: Mapping[str, Sequence[str]]) -> int:
    """Acerta as permissões dos módulos já instalados, na subida.

    Existe porque módulo **evolui**: a versão nova declara uma permissão que a anterior
    não tinha, e o papel de administrador das empresas que já usavam aquele módulo não a
    recebe por caminho nenhum — conceder na instalação só alcança quem instala depois.
    O sintoma é uma tela nova que abre em "permissão necessária", e foi assim que isto
    apareceu, com ``agro.pilot.read``.

    Silencioso quando nada foi registrado: o host sobe sem o ``core`` em teste de unidade,
    e ali não há empresa para acertar.
    """
    if _reconciler is None:
        return 0
    return await _reconciler(declared)
