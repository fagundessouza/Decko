# Ícones do Decko

Os ícones são desenho próprio do projeto, não biblioteca de terceiro. Regra de uso em
`docs/BRAND.md`, seção 2.2.

| Arquivo | O que é |
|---|---|
| `icones-folha-original.png` | A folha como veio do desenho: grade 7×5, 1536×1024, fundo já removido |
| `slice_icons.py` | Recorta a folha em um PNG por ícone |

Para gerar de novo os arquivos de `apps/web/src/assets/icons/`:

```bash
uv run --with pillow python docs/brand/slice_icons.py \
    docs/brand/icones-folha-original.png apps/web/src/assets/icons
```

O recorte não usa a grade como régua — ela não é exata, e cortar na borda da célula
levava pedaço do vizinho e decepava o que escapava dela, como a folha embaixo do drone.
Cada ícone é localizado pelo próprio canal alfa; a grade só decide quais pedaços são do
mesmo ícone. A saída é sempre 192×192, com o desenho centrado.

Os nomes da lista `NAMES` são a ordem de leitura da folha, e são eles que o `module.toml`
de cada módulo declara em `icon`. Quem resolve nome → arquivo é
`apps/web/src/components/ModuleIcon.tsx`, que importa só os que estão em uso: o alvo
inclui PC antigo de caixa, e os 35 juntos pesam mais de 1 MB.

Acrescentar um ícone à folha: desenhe na mesma grade, acrescente o nome na posição certa
de `NAMES`, rode o comando acima e importe o arquivo novo em `ModuleIcon.tsx`.
