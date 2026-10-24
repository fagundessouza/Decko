# ADR 0007 — Dependência entre módulos: só o que o manifesto declara

- **Data:** 2026-10-23
- **Status:** aceito
- **Substitui:** a regra de `docs/ARCHITECTURE.md` §2 — *"um módulo nunca importa diretamente
  de outro módulo irmão"*

## Contexto

A regra original existe por um motivo correto: o Odoo 20 tem 696 módulos que se importam em
teia, e o próprio projeto trata isso como dívida. Proibir o import de irmão foi a defesa
escolhida antes de existir um segundo módulo.

O PDV é o primeiro caso que a regra não cobre. Ele vende produto e baixa estoque — produto
e estoque são do módulo `comercial`, e o ADR 0006 já havia decidido o contrário da regra:
*"as verticais dependem dele"*.

Os três caminhos possíveis eram:

1. **Duplicar.** O PDV teria o seu próprio cadastro de produto. É exatamente o defeito que
   o ADR 0006 foi escrito para evitar.
2. **Só por evento.** Vender publicaria "venda finalizada" e o `comercial` reagiria. Mas o
   PDV precisa do preço e do saldo **durante** a venda, em tempo de resposta de caixa, e
   precisa que a baixa de estoque aconteça na mesma transação da venda. Evento resolve
   notificação, não leitura síncrona nem atomicidade.
3. **Importar o que o manifesto declara.** É o que o Odoo faz, e o que o carregador do
   Decko já sustenta: `depends` no `module.toml` existe desde o início e a ordem de
   carregamento já é resolvida por ele.

## Decisão

Um módulo pode importar de outro **se e somente se o declarar em `depends`**, direta ou
transitivamente, no `module.toml`.

A regra proibida passa a ser a específica: importar um módulo que não está declarado. Isso
é verificável, e é verificado — `apps/api/tests/test_module_boundaries.py` lê os imports de
cada módulo e compara com o manifesto. Um import não declarado quebra a suíte.

O que o emaranhado do Odoo tem e isto não: lá a dependência é descoberta lendo o código;
aqui ela está no manifesto, é o que ordena o carregamento, é o que a vitrine mostra antes
de instalar, e é o que o teste cobra.

## Consequências

- `pdv` declara `depends = ["core", "comercial"]` e chama `comercial.service` direto.
- Instalar um módulo instala o que ele depende — já implementado na vitrine.
- Desinstalar é recusado enquanto um módulo ativo depender dele. Sem isso, o PDV ficaria
  com telas que não abrem.
- O grafo de dependência continua sendo o do manifesto, então ele permanece legível: dá
  para desenhar o sistema sem abrir um `.py`.
- **Risco:** a disciplina agora depende de o `depends` ser honesto. Mitigação: o teste de
  fronteira, que falha no CI, e não a boa vontade de quem escreve o módulo.

## O que continua valendo

- Módulo irmão **não** altera tabela de outro módulo. Quem escreve em `comercial_movimento`
  é o serviço do `comercial`, chamado pelo PDV — não um `INSERT` do PDV.
- Extensão de entidade entre módulos (acrescentar coluna em tabela alheia) continua sem
  mecanismo e continua precisando de ADR — lacuna 4.2 do benchmark.
