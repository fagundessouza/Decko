"""O hash de senha não pode parar a API inteira.

Argon2id é caro de propósito — é disso que vive a proteção da senha. Medido na caixa do
piloto em 17/11/2026: 477 ms por conferência, com um worker de uvicorn. Chamado direto de
uma corrotina, esse tempo não é a espera de quem está entrando: é **todo mundo parado**,
porque o laço de eventos é um só.

No campo isso aparece como o PDV congelando no meio de uma venda porque alguém do outro
lado da cidade digitou a senha. O que estes testes guardam é que o cálculo acontece fora
do laço, e não quanto ele demora.
"""

import asyncio

import pytest

from decko_modules.core import security

SENHA = "uma-senha-qualquer-de-teste"


@pytest.fixture(scope="module")
def alvo() -> str:
    return security.hash_password(SENHA)


# Quantas vezes o trabalho se repete dentro da janela medida.
#
# Uma vez só não serve: numa máquina rápida o hash leva umas dezenas de milissegundos, e
# o `asyncio.sleep` no Windows acorda de 15 em 15 ms. A janela ficava menor que o próprio
# relógio, e o teste reprovava código correto. Repetir alarga a janela sem afrouxar o que
# se afirma.
REPETICOES = 3


async def _quantos_tiques_durante(fabrica) -> int:
    """Conta quantas vezes o laço conseguiu respirar enquanto o trabalho acontecia.

    Contar tiques, e não medir o atraso: máquina carregada atrasa qualquer medida de
    tempo, mas um laço que não está travado sempre consegue correr algumas vezes. Com o
    hash dentro do laço, esta conta dá **zero** — não um número pequeno.
    """
    tiques = 0

    async def pulsar() -> None:
        nonlocal tiques
        while True:
            await asyncio.sleep(0.005)
            tiques += 1

    vigia = asyncio.create_task(pulsar())
    await asyncio.sleep(0.05)  # deixa o vigia entrar em ritmo
    antes = tiques
    try:
        for _ in range(REPETICOES):
            await fabrica()
    finally:
        vigia.cancel()
    return tiques - antes


async def test_conferir_senha_deixa_o_laco_respirar(alvo: str) -> None:
    durante = await _quantos_tiques_durante(
        lambda: security.verify_password_async(SENHA, alvo)
    )
    # Com o cálculo dentro do laço, nenhum tique acontece enquanto ele roda.
    assert durante >= 4, f"o laço ficou parado durante a conferência ({durante} tiques)"


async def test_gerar_hash_deixa_o_laco_respirar() -> None:
    durante = await _quantos_tiques_durante(lambda: security.hash_password_async(SENHA))
    assert durante >= 4, f"o laço ficou parado durante o hash ({durante} tiques)"


async def test_a_conferencia_continua_dizendo_a_verdade(alvo: str) -> None:
    """Sair do laço não pode mudar a resposta — é a mesma conta, noutra thread."""
    assert await security.verify_password_async(SENHA, alvo) is True
    assert await security.verify_password_async("outra-senha-qualquer", alvo) is False


async def test_o_hash_gerado_fora_do_laco_vale_para_entrar() -> None:
    gerado = await security.hash_password_async(SENHA)
    assert await security.verify_password_async(SENHA, gerado) is True
    # E continua legível pelo caminho síncrono, que a linha de comando usa.
    assert security.verify_password(SENHA, gerado) is True


async def test_duas_conferencias_ao_mesmo_tempo_nao_se_enfileiram(alvo: str) -> None:
    """Duas pessoas entrando juntas não esperam uma pela outra.

    O ganho de vazão é modesto — o Argon2 já usa quatro threads por conta própria —, mas
    serializar seria o sintoma de o trabalho ter voltado para o laço.
    """
    inicio = asyncio.get_running_loop().time()
    await asyncio.gather(
        security.verify_password_async(SENHA, alvo),
        security.verify_password_async(SENHA, alvo),
    )
    juntas = asyncio.get_running_loop().time() - inicio

    inicio = asyncio.get_running_loop().time()
    await security.verify_password_async(SENHA, alvo)
    uma = asyncio.get_running_loop().time() - inicio

    # Margem larga de propósito: o que se recusa aqui é o dobro do tempo, que é como
    # ficaria se as duas voltassem a correr uma depois da outra.
    assert juntas < uma * 1.8, f"duas conferências levaram {juntas:.3f}s contra {uma:.3f}s"
