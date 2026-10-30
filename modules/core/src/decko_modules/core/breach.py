"""Conferência de senha conhecidamente vazada.

Mínimo de caracteres é aproximação do que importa. `Senha@123` tem oito caracteres,
maiúscula, número e símbolo, e está em toda lista de senha vazada que existe. A pergunta
direta é outra: **esta senha já apareceu num vazamento?**

A consulta manda os cinco primeiros caracteres hexadecimais do SHA-1 e recebe de volta
todos os sufixos daquele prefixo; a comparação acontece aqui dentro. O que sai é um
prefixo compartilhado por dezenas de milhares de senhas — a senha não sai, o hash inteiro
não sai.

O SHA-1 aqui **não é escolha de segurança**: é o formato do índice do serviço. O
armazenamento continua Argon2id, em ``security.py``.

Decisão, alternativas e o que foi deixado de fora:
``docs/adr/0011-senha-conhecidamente-vazada.md``.
"""

import hashlib
import logging

import httpx

logger = logging.getLogger(__name__)

API = "https://api.pwnedpasswords.com/range"

# Curto de propósito: isto está no caminho de alguém esperando numa tela, e a conferência
# falha aberta. Esperar muito por um "não sei" é o pior dos dois mundos.
TIMEOUT = 3.0

# Uma aparição já significa que a senha está em alguma lista que alguém usa para tentar.
# Não há limite a calibrar.
LIMITE = 1


class SenhaVazadaError(Exception):
    """A senha escolhida aparece em vazamento conhecido."""

    def __init__(self) -> None:
        # Sem o número de ocorrências: ele não ajuda quem vai escolher outra senha, e
        # "apareceu 3.251.237 vezes" é ruído com cara de precisão.
        super().__init__(
            "Esta senha aparece em vazamentos conhecidos e pode ser adivinhada em "
            "segundos. Escolha outra."
        )


def _prefixo_e_sufixo(password: str) -> tuple[str, str]:
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    return digest[:5], digest[5:]


def _ocorrencias(corpo: str, sufixo_procurado: str) -> int:
    """Lê a resposta do serviço: uma linha por sufixo, ``SUFIXO:contagem``."""
    for linha in corpo.splitlines():
        sufixo, _, contagem = linha.partition(":")
        if sufixo.strip().upper() == sufixo_procurado:
            try:
                return int(contagem.strip())
            except ValueError:
                # Linha malformada é problema do serviço, não motivo para recusar a senha.
                return 0
    return 0


async def ocorrencias(password: str, *, client: httpx.AsyncClient | None = None) -> int | None:
    """Quantas vezes a senha aparece em vazamento conhecido.

    Devolve ``None`` quando **não foi possível saber** — serviço fora do ar, rede ruim,
    tempo esgotado. Quem chama precisa distinguir isso de zero: zero é uma resposta,
    ``None`` é a ausência dela.

    O cliente entra por parâmetro para o teste não tocar a rede. Teste que depende de
    serviço de terceiro falha por motivo que não é o código.
    """
    prefixo, sufixo = _prefixo_e_sufixo(password)
    url = f"{API}/{prefixo}"
    # Sem o preenchimento, o tamanho da resposta é pista sobre o prefixo consultado.
    headers = {"Add-Padding": "true"}

    try:
        if client is not None:
            resposta = await client.get(url, headers=headers, timeout=TIMEOUT)
        else:
            async with httpx.AsyncClient(timeout=TIMEOUT) as proprio:
                resposta = await proprio.get(url, headers=headers, timeout=TIMEOUT)
        resposta.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("conferência de senha vazada não pôde ser feita: %s", exc)
        return None

    return _ocorrencias(resposta.text, sufixo)


async def recusar_se_vazada(
    password: str, *, habilitada: bool = True, client: httpx.AsyncClient | None = None
) -> None:
    """Levanta ``SenhaVazadaError`` quando a senha aparece em vazamento conhecido.

    Falha **aberta**: conferência que não pôde ser feita deixa a senha passar, e o fato
    fica no log. A alternativa seria impedir alguém de trabalhar porque um serviço de
    terceiro caiu — ver a decisão 2 do ADR 0011.
    """
    if not habilitada:
        return

    encontradas = await ocorrencias(password, client=client)
    if encontradas is not None and encontradas >= LIMITE:
        raise SenhaVazadaError
