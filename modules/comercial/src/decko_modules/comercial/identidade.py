"""Qual produto do cadastro é este item que chegou na nota.

O mesmo refrigerante vem ``COCA COLA 2L RET`` de um fornecedor e
``Refrigerante Coca-Cola 2 Litros Retornável`` de outro. Decidir que os dois são o mesmo
produto é o que impede o estoque de nascer com dois cadastros e meio saldo em cada.

Três chaves, em ordem de confiança — ver
``docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md``:

1. **GTIN igual.** Identidade global: o código de barras existe exatamente para dizer
   item, marca, modelo e tamanho. Liga sozinho.
2. **Mesmo código no mesmo fornecedor.** O emitente repete o ``cProd`` de nota para nota.
   Liga sozinho depois de o lojista confirmar uma vez.
3. **Nome parecido.** Nunca liga sozinho. Sugere, mostra a razão e espera o clique.

O NCM **não** é chave. Ele classifica a categoria — ``2202.10.00`` cobre Coca-Cola, Pepsi
e Guaraná, de todos os tamanhos. Aqui ele entra só como filtro negativo: NCM diferente
derruba o palpite.
"""

import unicodedata
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.comercial.models import Produto, ProdutoFornecedor

# Abaixo disto o palpite não é mostrado: sugestão ruim é pior que nenhuma, porque ensina
# o lojista a clicar sem ler.
LIMITE_SEMELHANCA = 0.45
MAXIMO_SUGESTOES = 5
# Prefixo mínimo para "ret" casar com "retornavel". Com duas letras, "re" casaria com
# meio dicionário.
PREFIXO_MINIMO = 3


class Origem(StrEnum):
    """Por que este produto foi apontado. É o que a tela mostra ao lojista."""

    GTIN = "gtin"
    FORNECEDOR = "fornecedor"
    SEMELHANCA = "semelhanca"


@dataclass(frozen=True)
class Candidato:
    produto_id: uuid.UUID
    nome: str
    origem: Origem
    # 1.0 quando a chave é identidade; a nota da semelhança quando é palpite.
    pontuacao: float

    @property
    def automatico(self) -> bool:
        """Se pode ligar sem perguntar.

        Semelhança de nome que acerta 95% das vezes erra o estoque em 5% das entradas, e
        ninguém descobre qual. Por isso ela nunca é automática.
        """
        return self.origem is not Origem.SEMELHANCA


def normalizar(texto: str) -> list[str]:
    """Quebra o nome em palavras comparáveis: sem acento, sem caixa, sem pontuação."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    limpo = "".join(
        caractere if caractere.isalnum() else " "
        for caractere in sem_acento
        if not unicodedata.combining(caractere)
    )
    return [palavra for palavra in limpo.lower().split() if palavra]


def _casa_palavra(palavra: str, outras: list[str]) -> bool:
    """Igual, ou uma é começo da outra — é assim que ``ret`` casa com ``retornavel``."""
    for outra in outras:
        if palavra == outra:
            return True
        if len(palavra) >= PREFIXO_MINIMO and outra.startswith(palavra):
            return True
        if len(outra) >= PREFIXO_MINIMO and palavra.startswith(outra):
            return True
    return False


def semelhanca(primeiro: str, segundo: str) -> float:
    """Quanto dois nomes de produto se parecem, de 0 a 1.

    A medida principal é **cobertura do nome curto dentro do longo**, e não a semelhança
    simétrica: o caso que importa é abreviação contra nome completo, onde o curto cabe
    inteiro no longo e o longo tem muita palavra a mais. Jaccard puniria exatamente o
    acerto.
    """
    palavras_a = normalizar(primeiro)
    palavras_b = normalizar(segundo)
    if not palavras_a or not palavras_b:
        return 0.0

    curto, longo = (
        (palavras_a, palavras_b) if len(palavras_a) <= len(palavras_b) else (palavras_b, palavras_a)
    )
    casadas = sum(1 for palavra in curto if _casa_palavra(palavra, longo))
    cobertura = casadas / len(curto)

    # A semelhança de sequência segura o caso em que a cobertura mente: duas palavras
    # curtas iguais dentro de nomes muito diferentes.
    sequencia = SequenceMatcher(None, " ".join(palavras_a), " ".join(palavras_b)).ratio()
    return round(0.7 * cobertura + 0.3 * sequencia, 4)


async def por_gtin(session: AsyncSession, gtin: str | None) -> Produto | None:
    if not gtin:
        return None
    return await session.scalar(select(Produto).where(Produto.gtin == gtin))


async def por_codigo_do_fornecedor(
    session: AsyncSession, *, fornecedor_cnpj: str, codigo_fornecedor: str
) -> Produto | None:
    """A equivalência que o lojista já confirmou uma vez."""
    vinculo = await session.scalar(
        select(ProdutoFornecedor).where(
            ProdutoFornecedor.fornecedor_cnpj == fornecedor_cnpj,
            ProdutoFornecedor.codigo_fornecedor == codigo_fornecedor,
        )
    )
    if vinculo is None:
        return None
    return await session.get(Produto, vinculo.produto_id)


async def identificar(
    session: AsyncSession,
    *,
    descricao: str,
    gtin: str | None = None,
    ncm: str | None = None,
    fornecedor_cnpj: str | None = None,
    codigo_fornecedor: str | None = None,
) -> list[Candidato]:
    """Os produtos que este item pode ser, do mais confiável para o menos.

    Devolve lista vazia quando não há nada parecido — é o caso de produto novo, e aí o
    lojista cadastra a partir da própria nota.
    """
    achado = await por_gtin(session, gtin)
    if achado is not None:
        return [
            Candidato(produto_id=achado.id, nome=achado.nome, origem=Origem.GTIN, pontuacao=1.0)
        ]

    if fornecedor_cnpj and codigo_fornecedor:
        achado = await por_codigo_do_fornecedor(
            session, fornecedor_cnpj=fornecedor_cnpj, codigo_fornecedor=codigo_fornecedor
        )
        if achado is not None:
            return [
                Candidato(
                    produto_id=achado.id,
                    nome=achado.nome,
                    origem=Origem.FORNECEDOR,
                    pontuacao=1.0,
                )
            ]

    return await _sugerir_por_nome(session, descricao=descricao, ncm=ncm)


async def _sugerir_por_nome(
    session: AsyncSession, *, descricao: str, ncm: str | None
) -> list[Candidato]:
    """Palpites ordenados. Nenhum deles liga sozinho.

    A comparação é feita na aplicação, e não no banco, porque a medida é de palavra e de
    prefixo — e o catálogo que chega aqui é o de uma empresa, não o do mundo. Quando isso
    pesar, entra índice de trigrama no PostgreSQL; medir antes.
    """
    produtos = list((await session.execute(select(Produto).where(Produto.ativo))).scalars().all())

    candidatos: list[Candidato] = []
    for produto in produtos:
        # NCM diferente é indício forte de que não é o mesmo item. Como filtro ele presta;
        # como identidade juntaria Coca-Cola com Pepsi, que dividem a mesma classificação.
        if ncm and produto.ncm and produto.ncm != ncm:
            continue

        pontuacao = semelhanca(descricao, produto.nome)
        if pontuacao < LIMITE_SEMELHANCA:
            continue

        candidatos.append(
            Candidato(
                produto_id=produto.id,
                nome=produto.nome,
                origem=Origem.SEMELHANCA,
                pontuacao=pontuacao,
            )
        )

    candidatos.sort(key=lambda candidato: (-candidato.pontuacao, candidato.nome))
    return candidatos[:MAXIMO_SUGESTOES]


async def lembrar_equivalencia(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    produto_id: uuid.UUID,
    fornecedor_cnpj: str,
    fornecedor_nome: str | None,
    codigo_fornecedor: str,
    descricao_fornecedor: str | None,
) -> ProdutoFornecedor:
    """Guarda a decisão do lojista para a próxima nota do mesmo fornecedor.

    Repetir a confirmação não é erro: o vínculo é atualizado, e não duplicado. O lojista
    pode ter ligado ao produto errado e estar corrigindo.
    """
    vinculo = await session.scalar(
        select(ProdutoFornecedor).where(
            ProdutoFornecedor.fornecedor_cnpj == fornecedor_cnpj,
            ProdutoFornecedor.codigo_fornecedor == codigo_fornecedor,
        )
    )

    if vinculo is None:
        vinculo = ProdutoFornecedor(
            tenant_id=tenant_id,
            produto_id=produto_id,
            fornecedor_cnpj=fornecedor_cnpj,
            codigo_fornecedor=codigo_fornecedor,
        )
        session.add(vinculo)

    vinculo.produto_id = produto_id
    vinculo.fornecedor_nome = fornecedor_nome
    vinculo.descricao_fornecedor = descricao_fornecedor
    await session.flush()
    return vinculo
