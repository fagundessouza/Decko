# ADR 0001 — Monólito modular em vez de microsserviços

- **Data:** 2026-10-19
- **Status:** aceito

## Contexto

O Decko precisa atender segmentos muito diferentes (agro, distribuidora, supermercado, restaurante,
veículos) com instalação por perfil de empresa, no modelo do Odoo. A stack escolhida inclui
ferramentas frequentemente associadas a arquitetura distribuída, e as anotações iniciais do projeto
mencionavam "microsserviços ou monólitos modulares bem delimitados".

Era preciso decidir antes de escrever código, porque a escolha determina o modelo de dados, o
deploy e o custo de operação.

## Decisão

Monólito modular: um processo de API que carrega módulos instaláveis em tempo de execução. A
fronteira entre módulos é lógica (manifesto, permissões, eventos), não de rede.

## Motivo

O time é de uma pessoa. Microsserviços resolvem escala organizacional e escala de carga
independente — nenhum dos dois é problema hoje. O que eles trazem de imediato é custo: deploy
distribuído, consistência eventual entre serviços, rastreamento obrigatório para qualquer
diagnóstico e multiplicação da superfície de falha.

O requisito real é **isolamento entre segmentos de negócio**, e isso é obtido pela disciplina de
módulo: um módulo não importa de um módulo irmão, depende apenas do `core` ou se comunica por
eventos.

Mantendo essa disciplina, extrair um módulo para serviço separado no futuro — se e quando houver
motivo de carga — vira trabalho mecânico, não reescrita.

## Consequências

- Deploy único; mais simples de operar e de hospedar para clientes pequenos.
- Transações entre módulos continuam sendo transações de banco, não sagas.
- **Risco:** sem disciplina, módulos passam a importar uns dos outros e o sistema vira um emaranhado.
  Mitigação: regra explícita em `CLAUDE.md` e verificação de dependência proibida no CI.
- Escalonamento é horizontal por réplica do processo inteiro, o que é adequado ao perfil de carga
  previsto.

## Alternativas consideradas

**Microsserviços desde o início** — descartado: custo operacional alto sem problema correspondente.

**Monólito sem módulos** — descartado: inviabiliza o requisito central de instalação por perfil de
empresa, que é o diferencial do produto.
