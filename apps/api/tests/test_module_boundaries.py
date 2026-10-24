"""A fronteira entre módulos, cobrada em vez de combinada.

Um módulo pode importar de outro só se o declarar em ``depends`` — ver
``docs/adr/0007-dependencia-entre-modulos.md``. Sem este teste a regra seria uma frase na
documentação, e o emaranhado de 696 módulos do Odoo começa exatamente por um import que
ninguém reparou.
"""

import ast
from pathlib import Path

import pytest

from decko.modules import ModuleManifest, discover

MODULES_DIR = Path(__file__).resolve().parents[3] / "modules"

NAMESPACE = "decko_modules"


def _imported_modules(source: Path) -> set[str]:
    """Os módulos irmãos citados num arquivo, pelo nome do pacote de namespace."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    citados: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            nomes = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # ``level`` > 0 é import relativo: nunca sai do próprio pacote.
            nomes = [node.module] if node.level == 0 and node.module else []
        else:
            continue

        for nome in nomes:
            partes = nome.split(".")
            if len(partes) >= 2 and partes[0] == NAMESPACE:
                citados.add(partes[1])

    return citados


def _allowed(manifest: ModuleManifest, manifests: dict[str, ModuleManifest]) -> set[str]:
    """O próprio módulo e tudo que ele declara, direta ou transitivamente."""
    permitido = {manifest.name}
    fila = list(manifest.depends)
    while fila:
        nome = fila.pop()
        if nome in permitido:
            continue
        permitido.add(nome)
        fila.extend(manifests[nome].depends)
    return permitido


def _manifests() -> dict[str, ModuleManifest]:
    return discover(MODULES_DIR)


@pytest.mark.parametrize("module_name", sorted(_manifests()))
def test_module_imports_only_what_it_declares(module_name: str) -> None:
    manifests = _manifests()
    manifest = manifests[module_name]
    permitido = _allowed(manifest, manifests)

    raiz = MODULES_DIR / module_name / "src" / NAMESPACE / module_name
    infracoes: list[str] = []

    for source in sorted(raiz.rglob("*.py")):
        for citado in _imported_modules(source) - permitido:
            infracoes.append(
                f"{source.relative_to(MODULES_DIR)} importa '{citado}', "
                f"que não está em depends de '{module_name}'"
            )

    assert not infracoes, "\n".join(infracoes)
