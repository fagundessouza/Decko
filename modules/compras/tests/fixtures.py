"""XML de NF-e para teste.

Fixture declarada, isolada e nunca carregada em produção — regra 1 do ``CLAUDE.md``. O
CNPJ e a chave são inventados; o layout é o da NF-e 4.00, que é o que está sendo lido.

As duas notas trazem **o mesmo refrigerante** com descrições diferentes, que é o caso
que o módulo existe para resolver: um fornecedor abrevia, o outro escreve por extenso.
"""

CNPJ_DISTRIBUIDOR_A = "11222333000181"
CNPJ_DISTRIBUIDOR_B = "44555666000172"

CHAVE_A = "35240111222333000181550010000000011000000017"
CHAVE_B = "35240144555666000172550010000000021000000028"

GTIN_COCA = "7894900011517"


def _nota(
    *,
    chave: str,
    numero: str,
    cnpj: str,
    nome: str,
    itens: str,
    valor: str,
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe versao="4.00" Id="NFe{chave}">
      <ide>
        <nNF>{numero}</nNF>
        <serie>1</serie>
        <dhEmi>2026-10-20T09:15:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>{cnpj}</CNPJ>
        <xNome>{nome}</xNome>
      </emit>
      {itens}
      <total>
        <ICMSTot>
          <vNF>{valor}</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
</nfeProc>
"""


# O fornecedor A abrevia tudo, e é assim que chega na vida real.
NOTA_DISTRIBUIDOR_A = _nota(
    chave=CHAVE_A,
    numero="1001",
    cnpj=CNPJ_DISTRIBUIDOR_A,
    nome="Distribuidora Alfa Ltda",
    valor="360.00",
    itens=f"""
      <det nItem="1">
        <prod>
          <cProd>CC2LRET</cProd>
          <xProd>COCA COLA 2L RET</xProd>
          <cEAN>{GTIN_COCA}</cEAN>
          <NCM>22021000</NCM>
          <uCom>UN</uCom>
          <qCom>24.0000</qCom>
          <vUnCom>7.5000</vUnCom>
          <vProd>180.00</vProd>
        </prod>
      </det>
      <det nItem="2">
        <prod>
          <cProd>ARZTJ5</cProd>
          <xProd>ARROZ TIO JOAO 5KG</xProd>
          <cEAN>SEM GTIN</cEAN>
          <NCM>10063021</NCM>
          <uCom>FD</uCom>
          <qCom>10.0000</qCom>
          <vUnCom>18.0000</vUnCom>
          <vProd>180.00</vProd>
        </prod>
      </det>""",
)

# O fornecedor B escreve por extenso. Mesmo refrigerante, mesmo código de barras.
NOTA_DISTRIBUIDOR_B = _nota(
    chave=CHAVE_B,
    numero="2002",
    cnpj=CNPJ_DISTRIBUIDOR_B,
    nome="Beta Comercio de Bebidas S/A",
    valor="78.00",
    itens=f"""
      <det nItem="1">
        <prod>
          <cProd>998877</cProd>
          <xProd>Refrigerante Coca-Cola 2 Litros Retornável</xProd>
          <cEAN>{GTIN_COCA}</cEAN>
          <NCM>22021000</NCM>
          <uCom>UN</uCom>
          <qCom>12.0000</qCom>
          <vUnCom>6.5000</vUnCom>
          <vProd>78.00</vProd>
        </prod>
      </det>""",
)

# Mesmo refrigerante, de um terceiro fornecedor, sem código de barras na nota: sobra a
# semelhança do nome, e aí o sistema sugere em vez de ligar sozinho.
NOTA_SEM_GTIN = _nota(
    chave="35240199888777000166550010000000031000000039",
    numero="3003",
    cnpj="99888777000166",
    nome="Gama Atacadista Ltda",
    valor="39.00",
    itens="""
      <det nItem="1">
        <prod>
          <cProd>REF-COCA-2L</cProd>
          <xProd>REFRIG COCA COLA 2L RETORNAVEL</xProd>
          <cEAN>SEM GTIN</cEAN>
          <NCM>22021000</NCM>
          <uCom>UN</uCom>
          <qCom>6.0000</qCom>
          <vUnCom>6.5000</vUnCom>
          <vProd>39.00</vProd>
        </prod>
      </det>""",
)

NAO_E_NOTA = "<html><body>Isto é um DANFE em PDF convertido errado</body></html>"
