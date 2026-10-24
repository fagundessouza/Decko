# ADR 0004 — Ativação de módulo por empresa

- **Data:** 2026-10-21
- **Status:** aceito
- **Fecha:** lacuna 4.1 de `docs/benchmark/odoo-20-comparativo.md`

## Contexto

O requisito central do produto é que *o cliente escolha o perfil da empresa e o sistema
fique pronto para aquele segmento*. Até aqui isso não acontecia: `load_into()` montava o
router de **todo** módulo descoberto para **todas** as empresas. O campo `required` existia
no manifesto e ninguém o lia. Uma distribuidora de bebidas enxergaria as rotas de
pulverização agrícola.

O Odoo não tem esse problema porque o registry é por banco: módulo não instalado não existe
naquele banco. O Decko usa banco único com Row Level Security (ADR 0002), então precisa de
mecanismo próprio.

Há um obstáculo de desenho. Quem monta as rotas é o host (`apps/api`), e é lá que a
verificação precisa estar para não depender de cada módulo lembrar de fazê-la. Mas
`docs/ARCHITECTURE.md` §2 proíbe o host de importar um módulo, e a tabela de empresas
pertence ao `core`. O host não pode simplesmente consultar `tenant_module` por conta
própria sem passar a conhecer o schema de um módulo.

## Decisão

**1. A ativação é um registro no banco.** Tabela `tenant_module` no módulo `core`:
`(tenant_id, module_name, activated_at, activated_by)`, com RLS como qualquer tabela de
empresa. Ausência de linha significa módulo inativo — o padrão é negar.

**2. O host define a porta; o `core` a implementa.** `decko/activation.py` guarda um
registro de verificação. O `core`, ao ser importado, registra a sua implementação. O host
chama através da porta e nunca importa o módulo.

A inversão existe porque a alternativa — o host consultando `tenant_module` em SQL cru —
faria o host conhecer uma tabela que não é dele, que é exatamente o acoplamento que a
arquitetura evita.

**3. A verificação é montada pelo host, não escrita pelo módulo.** `load_into()` acrescenta
a dependência de ativação ao router de cada módulo não obrigatório. Um módulo não tem como
esquecer de se proteger, porque não é ele quem se protege.

**4. `required = true` dispensa verificação.** O `core` é obrigatório: sem ele não há como
autenticar, e verificar ativação para poder verificar ativação não fecha.

**5. Módulo inativo responde 404, não 403.** 403 diz "existe e você não pode"; 404 diz "não
faz parte do seu sistema", que é a verdade para quem não contratou o módulo, e não revela a
composição comercial de outras empresas.

## Consequências

- Permissão e ativação passam a ser coisas distintas. O papel de administrador recebe as
  permissões de todos os módulos instalados na plataforma (vêm dos manifestos), mas só
  alcança as rotas dos módulos ativos naquela empresa. Quem decide é a ativação.
- `/auth/me` passa a informar os módulos ativos. A interface deixa de inferir o menu a
  partir do prefixo das permissões, que era uma coincidência e não um contrato.
- O `bootstrap` ganha `--module`, e sem ele a empresa nasce só com o núcleo. Isso quebra
  deliberadamente qualquer fluxo que presumia tudo ligado: é o comportamento correto e é
  melhor que apareça num teste do que num cliente.
- **Perfil de segmento fica para depois.** Um perfil ("supermercado", "distribuidora") é um
  conjunto nomeado de módulos, uma camada fina sobre esta. Não faz sentido nomear conjuntos
  antes de existirem módulos para agrupar.
- Desativar não apaga dado: a linha sai de `tenant_module` e as tabelas do módulo
  permanecem. Remover dado de módulo desinstalado depende da lacuna 4.3 (identidade estável
  para dados de módulo) e não é resolvido aqui.

## Alternativas consideradas

**Filtrar o menu no frontend** — descartado como mecanismo único: é aparência, não controle
de acesso. Continua valendo como complemento, alimentado por `/auth/me`.

**Verificar dentro de `require(permission)`, deduzindo o módulo pelo prefixo da string** —
tentador porque não exigiria mudança no host. Descartado: uma rota que esquecesse de
declarar permissão ficaria sem nenhuma verificação. A proteção precisa vir da montagem, que
nenhum módulo consegue contornar por omissão.

**Registry por banco, como o Odoo** — descartado em ADR 0002. Resolveria isto de graça, ao
custo de um banco por cliente.
