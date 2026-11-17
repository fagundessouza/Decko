"""Hash de senha e emissão de tokens."""

import asyncio
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


# Oito, que é o piso do NIST 800-63B. O valor anterior, 12, era escolha arbitrária e
# recusava senha que o próprio dono da conta queria usar.
#
# Comprimento alto não é o que protege a conta: o que protege é o hash Argon2id, o tempo
# de resposta igualado no login e a recusa de senha conhecidamente vazada (ADR 0011).
#
# Mora aqui, e não no comando de bootstrap, porque o cadastro de usuário pela interface
# precisa do mesmo piso — dois números diferentes para a mesma coisa é como um deles fica
# para trás.
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


async def hash_password_async(password: str) -> str:
    """O mesmo hash, numa thread, para quem chama de dentro do laço de eventos.

    Argon2id é caro **de propósito** — é disso que vive a proteção da senha. Medido na
    caixa do piloto em 17/11/2026: 477 ms por conferência. Chamado direto de uma corrotina,
    esse tempo não é só a espera de quem está entrando: é a API inteira parada, porque o
    laço de eventos é um só. Com um operador no meio de uma venda, a tela dele congela
    porque alguém do outro lado da cidade digitou a senha.

    A mesma medição com `asyncio.to_thread`: o laço deixou de parar 483 ms e passou a
    parar 2 ms. A vazão melhora pouco (1,7x), porque o Argon2 já usa quatro threads por
    conta própria — o que muda é que o resto do sistema continua respondendo.

    Funciona porque o argon2-cffi solta o GIL durante o cálculo, que acontece em C. Se não
    soltasse, mudar de thread não adiantaria nada, e por isso isto foi medido antes de ser
    escrito.
    """
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    """A conferência fora do laço de eventos. Ver `hash_password_async`."""
    return await asyncio.to_thread(verify_password, password, password_hash)


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
