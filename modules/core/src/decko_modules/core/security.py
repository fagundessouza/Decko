"""Hash de senha e emissão de tokens."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from decko.config import get_settings

ALGORITHM = "HS256"

# Argon2id é a recomendação atual da OWASP para hash de senha. Os parâmetros padrão da
# biblioteca já seguem essa recomendação; fixá-los aqui seria congelar valores que devem
# acompanhar a evolução da biblioteca.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def needs_rehash(password_hash: str) -> bool:
    """Indica que o hash foi gerado com parâmetros antigos e deve ser regravado no próximo
    login bem-sucedido, quando a senha em claro está disponível."""
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    permissions: list[str],
) -> tuple[str, int]:
    settings = get_settings()
    ttl = settings.access_token_ttl_seconds
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "perms": permissions,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), ttl


def decode_access_token(token: str) -> dict[str, Any]:
    """Levanta ``jwt.PyJWTError`` quando o token é inválido ou expirou."""
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("tipo de token inesperado")
    return payload


REFRESH_SEPARATOR = "."


def new_refresh_token(tenant_id: uuid.UUID) -> tuple[str, str]:
    """Devolve (token em claro, hash a persistir).

    O refresh token é um valor aleatório opaco, não um JWT: ele precisa ser revogável, e
    revogar exige consultar o armazenamento de qualquer forma — assinar não traria ganho.

    O identificador da empresa vai em claro no início do token porque a tabela que o
    guarda tem Row Level Security: sem saber a empresa antes da consulta, a busca não
    encontraria o próprio token. Isso não é segredo — é o endereço da gaveta, não a chave.
    """
    raw = f"{tenant_id}{REFRESH_SEPARATOR}{secrets.token_urlsafe(48)}"
    return raw, hash_refresh_token(raw)


def tenant_from_refresh_token(raw: str) -> uuid.UUID:
    """Extrai a empresa do token. Levanta ``ValueError`` se o formato não bater."""
    prefix, separator, remainder = raw.partition(REFRESH_SEPARATOR)
    if not separator or not remainder:
        raise ValueError("formato de refresh token inválido")
    return uuid.UUID(prefix)


def hash_refresh_token(raw: str) -> str:
    # SHA-256 é suficiente: o token já tem entropia alta, então não há ataque de
    # dicionário a mitigar, e a verificação acontece a cada renovação.
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
