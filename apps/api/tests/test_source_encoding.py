"""Garante que nenhum arquivo do projeto tenha acento corrompido.

A documentação e a interface são em português. Uma ferramenta que regrave um arquivo na
página ANSI do Windows corrompe os acentos em silêncio: o código continua executando, os
testes continuam passando, e o estrago só aparece quando alguém lê o texto.

Este teste existe porque isso já aconteceu uma vez neste repositório.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRS = {"node_modules", ".venv", ".git", "dist", "__pycache__", ".ruff_cache"}
SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".md",
    ".toml",
    ".css",
    ".json",
    ".html",
    ".ini",
    ".mako",
}

# Caracteres acentuados comuns em português e no texto deste projeto.
ACCENTED = "áâãçéêíóôõúü—"


def _corrupt(character: str) -> str | None:
    """Produz a forma corrompida de um caractere: seus bytes UTF-8 lidos como cp1252."""
    try:
        return character.encode("utf-8").decode("cp1252")
    except UnicodeDecodeError:
        # Alguns bytes não têm correspondente em cp1252; esses nunca aparecem corrompidos.
        return None


# Derivado, em vez de escrito literalmente, por dois motivos: escrito à mão, este arquivo
# acusaria a si mesmo; e o formatador converte escapes de volta em caracteres literais,
# desfazendo qualquer tentativa de escondê-los.
MOJIBAKE = tuple(filter(None, (_corrupt(character) for character in ACCENTED)))


def source_files() -> list[Path]:
    return [
        path
        for path in REPO_ROOT.rglob("*")
        if path.is_file()
        and path.suffix in SOURCE_SUFFIXES
        and not SKIP_DIRS.intersection(path.parts)
    ]


def test_markers_were_derived() -> None:
    """Se a derivação falhasse, a lista ficaria vazia e tudo passaria sem verificar nada."""
    assert len(MOJIBAKE) >= 10


def test_there_are_files_to_check() -> None:
    """Sem isto, um erro de caminho faria o teste passar sem verificar nada."""
    assert len(source_files()) > 20


@pytest.mark.parametrize("path", source_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_file_is_valid_utf8_without_mojibake(path: Path) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        pytest.fail(f"{path.relative_to(REPO_ROOT)} não é UTF-8 válido: {exc}")

    found = [marker for marker in MOJIBAKE if marker in content]
    assert not found, (
        f"{path.relative_to(REPO_ROOT)} tem acento corrompido. "
        "Reescreva o arquivo em UTF-8; não use Set-Content do PowerShell em código-fonte."
    )
