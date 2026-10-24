# ADR 0005 — Perfil de segmento

- **Data:** 2026-10-21
- **Status:** aceito
- **Depende de:** ADR 0004 (ativação de módulo por empresa)

## Contexto

O requisito de produto é o cliente escolher o segmento e o sistema ficar pronto para ele —
supermercado, ferragista, lanchonete, distribuidora. A ativação por empresa já existe
(ADR 0004), mas obriga quem está entrando a saber **quais** módulos o seu ramo usa, que é
justamente o que ele não sabe e não deveria precisar saber.

A auditoria do Odoo 20 mostra como o mecanismo funciona lá, e o que ele tem de duas partes
(ver `docs/benchmark/odoo-20-comparativo.md` §4.3):

1. **Conjunto de módulos.** `pos_restaurant` declara uma única dependência,
   `point_of_sale`. A vertical é fina; o peso está na base compartilhada.
2. **Dado-semente com identidade estável.** O grosso de `pos_restaurant` são registros em
   `data/scenarios/`, com identificador externo resolvido por `ir.model.data` e marcados
   `noupdate="1"` — a semente é ponto de partida, e atualizar o módulo não sobrescreve o
   que o cliente já ajustou.

## Decisão

**Implementar agora apenas a parte 1: perfil como conjunto nomeado de módulos.**

Um perfil é um arquivo em `profiles/<nome>.toml`, descoberto pelo host do mesmo jeito que
os manifestos de módulo. Ativar um perfil é ativar os módulos que ele lista, usando o
mecanismo que já existe.

**Adiar a parte 2 — dado-semente — até existir módulo que tenha semente para carregar.**

Hoje nenhum módulo traz catálogo, unidade ou categoria. Construir o carregador de semente
agora seria abstração sem consumidor, e `CLAUDE.md` veda isso. Quando a base comercial
existir, a semente vira necessária e exige antes a lacuna 4.3 (identidade estável), sem a
qual a carga não é idempotente nem reversível.

O perfil fica sendo, portanto, uma **lista de módulos** — e não um pacote de configuração.
Isso é dito aqui para que a diferença não se perca: o "um clique" entregue nesta decisão
liga os módulos certos; ele ainda não popula catálogo nenhum.

## Consequências

- Ativar um perfil é idempotente porque ativar módulo já é (ADR 0004). Repetir não quebra.
- **Perfil não é vínculo.** A empresa não "é" um supermercado; ela tem módulos ativos. O
  perfil é um atalho de contratação, e o que vale depois é o conjunto de módulos. Isso
  evita a pergunta "o que acontece quando o cliente muda de ramo": nada, ele liga e desliga
  módulos.
- Desativar um perfil desliga os módulos dele que não são obrigatórios. Como perfis podem
  compartilhar módulo, desligar um perfil pode remover módulo que outro também usava — por
  isso a desativação é por módulo, e não existe "desativar perfil".
- Um perfil que liste módulo inexistente é recusado na leitura, não na ativação: erro de
  empacotamento aparece na inicialização, não na frente do cliente.

## Alternativas consideradas

**Perfil como coluna em `tenant`** — descartado: faria a empresa "ser" de um segmento, e aí
mudar de ramo ou operar dois (mercado com lanchonete dentro) vira caso especial. Módulos
ativos já respondem isso sem exceção.

**Perfil declarado no manifesto de cada módulo** (`segments = ["supermercado"]`) —
descartado: espalha a definição do perfil por N arquivos, e ninguém consegue responder
"o que compõe o perfil supermercado" sem varrer todos os módulos.

**Esperar a base comercial para fazer tudo junto** — descartado: o conjunto de módulos é
útil sozinho e já é o que falta para contratar um cliente novo sem instrução manual.
