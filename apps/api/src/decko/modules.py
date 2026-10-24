"""Descoberta e carregamento de módulos de negócio.

Um módulo é um pacote Python com um manifesto ``module.toml``. O host lê os manifestos,
resolve a ordem de dependência e importa cada pacote, montando o router que ele expõe.

Esta é a mecânica que sustenta o requisito central do produto: instalar o perfil de uma
empresa é ativar um conjunto de módulos, não espalhar condicionais pelo código.
"""

import importlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI

from decko.activation import activation_guard_for

API_PREFIX = "/api/v1"


class ModuleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModuleManifest:
    name: str
    label: str
    version: str
    package: str
    depends: tuple[str, ...] = ()
    required: bool = False
    branch_label: str | None = None
    permissions: tuple[str, ...] = ()
    menu: dict[str, object] = field(default_factory=dict)

    # Como o módulo aparece na vitrine. Fica no manifesto, e não numa lista na interface,
    # porque senão acrescentar um módulo exigiria lembrar de editar dois lugares — e um
    # deles ficaria para trás.
    category: str = "Outros"
    summary: str = ""
    icon: str = "apps"
    # Cor de identidade do módulo na vitrine. Nome do papel, não valor: a cor mora nos
    # tokens — ver docs/BRAND.md, seção 2.1.
    accent: str = "slate"

    @classmethod
    def from_file(cls, path: Path) -> "ModuleManifest":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        try:
            module = data["module"]
            menu = data.get("menu", {})
            return cls(
                name=module["name"],
                label=module.get("label", module["name"]),
                version=module["version"],
                package=module["package"],
                depends=tuple(module.get("depends", [])),
                required=bool(module.get("required", False)),
                branch_label=data.get("migrations", {}).get("branch_label"),
                permissions=tuple(data.get("permissions", {}).get("provides", [])),
                menu=menu,
                category=module.get("category", "Outros"),
                summary=module.get("summary", ""),
                # Nome do ícone, não símbolo: a arte mora na interface, que a resolve
                # pelo nome — ver apps/web/src/components/ModuleIcon.tsx.
                icon=str(module.get("icon") or "apps"),
                accent=str(module.get("accent") or "slate"),
            )
        except KeyError as exc:
            raise ModuleError(f"{path}: campo obrigatório ausente: {exc}") from exc


def discover(modules_dir: Path) -> dict[str, ModuleManifest]:
    """Lê todos os manifestos. Diretórios sem module.toml são ignorados — é assim que um
    módulo ainda não implementado convive no repositório sem quebrar a inicialização."""
    manifests: dict[str, ModuleManifest] = {}
    for manifest_path in sorted(modules_dir.glob("*/module.toml")):
        manifest = ModuleManifest.from_file(manifest_path)
        if manifest.name in manifests:
            raise ModuleError(f"módulo duplicado: {manifest.name}")
        manifests[manifest.name] = manifest
    return manifests


def resolve_order(manifests: dict[str, ModuleManifest]) -> list[ModuleManifest]:
    """Ordena por dependência. Levanta erro em dependência ausente ou ciclo, em vez de
    deixar o problema aparecer como um import quebrado mais adiante."""
    ordered: list[ModuleManifest] = []
    done: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if name in done:
            return
        if name in visiting:
            cycle = " -> ".join([*trail, name])
            raise ModuleError(f"dependência circular entre módulos: {cycle}")
        manifest = manifests.get(name)
        if manifest is None:
            origin = trail[-1] if trail else "?"
            raise ModuleError(f"módulo '{origin}' depende de '{name}', que não existe")
        visiting.add(name)
        for dependency in manifest.depends:
            visit(dependency, (*trail, name))
        visiting.discard(name)
        done.add(name)
        ordered.append(manifest)

    for name in manifests:
        visit(name, ())
    return ordered


def with_dependencies(name: str, manifests: dict[str, ModuleManifest]) -> list[str]:
    """O módulo pedido e tudo de que ele precisa, em ordem de dependência.

    Quem contrata escolhe o que quer fazer, não a árvore técnica por baixo. Ativar um
    módulo sem o que ele usa deixaria a empresa com uma tela que não abre.
    """
    resolvido: list[str] = []

    def visit(atual: str) -> None:
        if atual in resolvido:
            return
        manifest = manifests[atual]
        for dependency in manifest.depends:
            visit(dependency)
        resolvido.append(atual)

    visit(name)
    return resolvido


def dependents(name: str, manifests: dict[str, ModuleManifest]) -> list[str]:
    """Os módulos que deixariam de funcionar se este saísse — direta ou indiretamente."""
    return sorted(
        other.name
        for other in manifests.values()
        if other.name != name and name in with_dependencies(other.name, manifests)
    )


def load_into(app: FastAPI, modules_dir: Path) -> list[ModuleManifest]:
    """Importa cada módulo e monta seu router em /api/v1/<nome>."""
    loaded: list[ModuleManifest] = []
    for manifest in resolve_order(discover(modules_dir)):
        try:
            package = importlib.import_module(manifest.package)
        except ImportError as exc:
            raise ModuleError(
                f"módulo '{manifest.name}': não foi possível importar "
                f"'{manifest.package}'. O pacote está instalado no workspace?"
            ) from exc

        router = getattr(package, "router", None)
        if router is None:
            raise ModuleError(f"módulo '{manifest.name}': o pacote não expõe 'router'")
        if not isinstance(router, APIRouter):
            raise ModuleError(f"módulo '{manifest.name}': 'router' não é um APIRouter")

        # Módulo obrigatório não é verificado: o núcleo é o que permite autenticar, e
        # exigir ativação para poder conferir ativação não fecha.
        # A verificação é acrescentada aqui, na montagem, e não escrita dentro do módulo:
        # assim nenhum módulo consegue ficar desprotegido por esquecimento.
        guards = [] if manifest.required else [Depends(activation_guard_for(manifest.name))]

        app.include_router(
            router,
            prefix=f"{API_PREFIX}/{manifest.name}",
            tags=[manifest.name],
            dependencies=guards,
        )
        loaded.append(manifest)
    return loaded
