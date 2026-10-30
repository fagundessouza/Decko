"""Recusa de senha conhecidamente vazada.

Nenhum teste aqui toca a rede: a conferência recebe o cliente HTTP por parâmetro, e cada
teste responde o que precisa. Teste que depende de serviço de terceiro falha por motivo
que não é o código — e a suíte inteira roda com a conferência desligada, ver `conftest.py`.

Decisão: `docs/adr/0011-senha-conhecidamente-vazada.md`.
"""

import hashlib

import httpx
import pytest

from decko_modules.core.breach import SenhaVazadaError, ocorrencias, recusar_se_vazada

# A senha mais previsível que existe, e o motivo de a conferência existir: ela passa em
# qualquer regra de composição razoável depois do `@1`.
VAZADA = "Senha@123"
INEDITA = "cavalo-bateria-grampo-correto-47"


def _sufixo(password: str) -> str:
    return hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()[5:]


def _servico(corpo: str, status: int = 200) -> httpx.AsyncClient:
    """Um cliente que responde o que o teste mandar, sem sair da máquina."""

    async def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=corpo)

    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


async def test_senha_que_aparece_em_vazamento_e_recusada() -> None:
    corpo = f"{_sufixo(VAZADA)}:24230\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:3"

    async with _servico(corpo) as cliente:
        with pytest.raises(SenhaVazadaError) as recusa:
            await recusar_se_vazada(VAZADA, client=cliente)

    # A contagem não entra na mensagem: não ajuda quem vai escolher outra senha.
    assert "24230" not in str(recusa.value)
    assert "Escolha outra" in str(recusa.value)


async def test_senha_ausente_da_lista_passa() -> None:
    corpo = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:3\nBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB:9"

    async with _servico(corpo) as cliente:
        await recusar_se_vazada(INEDITA, client=cliente)


async def test_so_o_prefixo_do_hash_sai_daqui() -> None:
    """O ponto do k-anonimato: a senha e o hash inteiro não saem da máquina."""
    vistas: list[str] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        vistas.append(str(request.url))
        return httpx.Response(200, text="")

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        await ocorrencias(VAZADA, client=cliente)

    digest = hashlib.sha1(VAZADA.encode(), usedforsecurity=False).hexdigest().upper()
    assert vistas[0].endswith(f"/{digest[:5]}")
    assert digest not in vistas[0]
    assert VAZADA not in vistas[0]


async def test_pede_preenchimento_na_resposta() -> None:
    """Sem o preenchimento, o tamanho da resposta é pista sobre o prefixo consultado."""
    cabecalhos: list[httpx.Headers] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        cabecalhos.append(request.headers)
        return httpx.Response(200, text="")

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        await ocorrencias(VAZADA, client=cliente)

    assert cabecalhos[0]["add-padding"] == "true"


async def test_servico_fora_do_ar_deixa_a_senha_passar() -> None:
    """Falha aberta. A alternativa é ninguém conseguir trabalhar porque um terceiro caiu."""

    async def cair(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede")

    async with httpx.AsyncClient(transport=httpx.MockTransport(cair)) as cliente:
        await recusar_se_vazada(VAZADA, client=cliente)
        assert await ocorrencias(VAZADA, client=cliente) is None


async def test_resposta_de_erro_deixa_a_senha_passar() -> None:
    async with _servico("", status=503) as cliente:
        await recusar_se_vazada(VAZADA, client=cliente)


async def test_nao_saber_e_diferente_de_zero() -> None:
    """``None`` é a ausência de resposta; zero é uma resposta. Confundir falha fechado."""
    async with _servico("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:3") as cliente:
        assert await ocorrencias(INEDITA, client=cliente) == 0

    async with _servico("", status=500) as cliente:
        assert await ocorrencias(INEDITA, client=cliente) is None


async def test_desligada_nao_consulta_nada() -> None:
    """Instalação sem internet: a conferência é latência garantida sem resposta possível."""

    async def nunca(request: httpx.Request) -> httpx.Response:
        raise AssertionError("não devia consultar com a conferência desligada")

    async with httpx.AsyncClient(transport=httpx.MockTransport(nunca)) as cliente:
        await recusar_se_vazada(VAZADA, habilitada=False, client=cliente)


async def test_linha_malformada_nao_recusa_a_senha() -> None:
    """Problema do serviço não vira senha recusada na cara de quem está cadastrando."""
    async with _servico(f"{_sufixo(VAZADA)}:nao-e-numero") as cliente:
        await recusar_se_vazada(VAZADA, client=cliente)
