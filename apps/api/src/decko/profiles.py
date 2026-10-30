"""Perfis de segmento: conjuntos nomeados de módulos.

Quem está contratando sabe o ramo do seu negócio, não quais módulos ele usa. O perfil é o
atalho entre as duas coisas.

Um perfil é uma lista de módulos, e não um pacote de configuração: ativar o perfil liga os
módulos certos, mas não popula catálogo nenhum. Dado-semente depende da lacuna 4.3 do
benchmark e está adiado — ver ``docs/adr/0005-perfil-de-segmento.md``.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from decko.modules import ModuleManifest


class ProfileError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    label: str
    description: str
    modules: tuple[str, ...]

    @classmethod
    def from_file(cls, path: Path) -> "Profile":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        try:
            profile = data["profile"]
            return cls(
                name=profile["name"],
                label=profile["label"],
                description=profile.get("description", ""),
                modules=tuple(profile["modules"]),
            )
        except KeyError as exc:
            raise ProfileError(f"{path}: campo obrigatório ausente: {exc}") from exc


def discover(profiles_dir: Path, manifests: dict[str, ModuleManifest]) -> dict[str, Profile]:
    """Lê os perfis e confere cada módulo listado contra os manifestos instalados.

    A conferência acontece aqui, na leitura, e não na ativação: erro de empacotamento deve
    aparecer na inicialização, não na frente de quem está contratando.
    """
    if not profiles_dir.is_dir():
        return {}

    profiles: dict[str, Profile] = {}
    for path in sorted(profiles_dir.glob("*.toml")):
        profile = Profile.from_file(path)

        if profile.name in profiles:
            raise ProfileError(f"perfil duplicado: {profile.name}")

        desconhecidos = [name for name in profile.modules if name not in manifests]
        if desconhecidos:
            raise ProfileError(
                f"perfil '{profile.name}' lista módulo que não existe: {', '.join(desconhecidos)}"
            )

        profiles[profile.name] = profile

    return profiles


def modules_to_activate(profile: Profile, manifests: dict[str, ModuleManifest]) -> list[str]:
    """Os módulos do perfil que precisam de linha de ativação.

    Obrigatório já vale como ativo; gravar linha para ele seria redundante.
    """
    return [name for name in profile.modules if not manifests[name].required]
