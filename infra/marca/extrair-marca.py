"""Tira a marca do fundo da arte que o Lucas mandou.

A arte vem com fundo claro em degradê e formas verdes nos cantos. O cabeçalho do site é
branco, então o que precisa sair daqui é a marca recortada com fundo transparente — e
transparente de verdade, não um retângulo branco por cima de outro branco.

O método: a tinta é escura (azul-petróleo) ou verde saturada, e o fundo é claro e sem
saturação. O alfa sai da distância entre a luminância do pixel e a do fundo, e depois a cor
é "desmisturada" do fundo, senão a borda antisserrilhada carrega um halo claro que aparece
em qualquer fundo que não seja branco.

Uso, com a arte oficial em mãos:

    uv run --with pillow python infra/marca/extrair-marca.py infra/marca/decko-marca.webp

As coordenadas abaixo valem para a arte entregue em 19/11/2026 (1672x941). Se a arte for
reexportada noutro tamanho, confira os cortes antes de confiar no resultado.
"""

import pathlib
import sys

from PIL import Image, ImageDraw, ImageFilter

if len(sys.argv) != 2:
    raise SystemExit("uso: extrair-marca.py <arte.webp|png|jpg>")

ORIGEM = pathlib.Path(sys.argv[1])
DESTINO = pathlib.Path(__file__).resolve().parents[2] / "apps" / "site"

arte = Image.open(ORIGEM).convert("RGB")

# O fundo, estimado por um borrão largo da própria arte: ele acompanha o degradê em vez de
# supor um branco chapado que não existe.
fundo = arte.filter(ImageFilter.GaussianBlur(radius=60))


def recortar(caixa):
    """Recorta a caixa e devolve RGBA com o fundo claro virado em transparência."""
    x0, y0, x1, y1 = caixa
    pedaco = arte.crop(caixa)
    fpedaco = fundo.crop(caixa)
    larg, alt = pedaco.size
    saida = Image.new("RGBA", (larg, alt), (0, 0, 0, 0))

    po, pf, ps = pedaco.load(), fpedaco.load(), saida.load()
    for y in range(alt):
        for x in range(larg):
            r, g, b = po[x, y]
            fr, fg, fb = pf[x, y]
            luz = (r + g + b) / 3
            luz_fundo = max((fr + fg + fb) / 3, 200)

            # 6 de folga mata a poeira do degradê sem comer a borda da letra.
            a = (luz_fundo - luz - 6) / 114
            a = 0.0 if a < 0 else (1.0 if a > 1 else a)
            if a <= 0:
                continue

            cor = []
            for obs, fnd in ((r, fr), (g, fg), (b, fb)):
                v = (obs - (1 - a) * fnd) / a
                cor.append(0 if v < 0 else (255 if v > 255 else int(round(v))))
            ps[x, y] = (cor[0], cor[1], cor[2], int(round(a * 255)))
    return saida


# ------------------------------------------------------------------ a marca escrita
# x 241..1407, y 309..543 é a palavra inteira; a folga de 6px evita cortar o antisserrilhado.
marca = recortar((235, 303, 1413, 549))
marca = marca.resize((417, 87), Image.LANCZOS)
marca.save(DESTINO / "marca.png", optimize=True)

# ------------------------------------------------------------------ só o símbolo
# A folha e o D, até a primeira coluna vazia da palavra (x 564). É o que cabe no cabeçalho
# do celular, onde a palavra inteira empurraria o botão para fora da tela.
simbolo = recortar((235, 303, 570, 549))
simbolo.resize((123, 90), Image.LANCZOS).save(DESTINO / "simbolo.png", optimize=True)

# ------------------------------------------------------------------ o ícone da aba
# Quadrado branco com cantos arredondados: o D é azul-petróleo e sumiria num fundo escuro,
# e a aba do navegador pode ser clara ou escura.
LADO = 180
icone = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
mascara = Image.new("L", (LADO, LADO), 0)
ImageDraw.Draw(mascara).rounded_rectangle((0, 0, LADO - 1, LADO - 1), radius=38, fill=255)
icone.paste(Image.new("RGBA", (LADO, LADO), (255, 255, 255, 255)), (0, 0), mascara)

s = recortar((235, 303, 570, 549))
alvo = 108
s = s.resize((int(alvo * s.width / s.height), alvo), Image.LANCZOS)
icone.alpha_composite(s, ((LADO - s.width) // 2, (LADO - alvo) // 2))
icone.save(DESTINO / "favicon.png", optimize=True)
icone.save(DESTINO / "apple-touch-icon.png", optimize=True)

# ------------------------------------------------------------------ a imagem do link
# 1200x630 é o que WhatsApp e LinkedIn esperam. A arte é 16:9, então sobra altura: o corte
# centralizado mantém a palavra, a assinatura e as formas dos cantos.
LARG, ALT = 1200, 630
alt_corte = round(arte.width * ALT / LARG)
topo = (arte.height - alt_corte) // 2
og = arte.crop((0, topo, arte.width, topo + alt_corte)).resize((LARG, ALT), Image.LANCZOS)
og.save(DESTINO / "og.png", optimize=True)

for nome in ("marca.png", "simbolo.png", "favicon.png", "apple-touch-icon.png", "og.png"):
    arq = DESTINO / nome
    print(f"{nome}: {Image.open(arq).size} {arq.stat().st_size // 1024} KB")
