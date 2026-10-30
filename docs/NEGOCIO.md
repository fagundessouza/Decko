# O negócio do Decko — posicionamento, estado e o que falta para vender

**Para que serve este documento.** O `ROADMAP.md` responde *o que construir e em que ordem*.
Ele não responde *o que isto é, para quem, e o que falta para alguém pagar* — e essa é
justamente a linha que se perde depois de meses dentro do código. Este arquivo existe para
ela ser reencontrada sem precisar reconstituí-la de memória.

**Última revisão:** 29/10/2026.

> **Como ler.** As seções 1 a 3 são **o que foi decidido** e vêm do `README.md` e do
> `CLAUDE.md`. A seção 4 é **fato conferido no repositório**. As seções 5 e 6 separam
> **bloqueio** de **recomendação** — a primeira é constatação, a segunda é opinião, e elas
> não valem a mesma coisa.

---

## 1. O que o Decko é

Plataforma ERP/PDV modular, **Open Core**, no modelo do Odoo: o cliente escolhe o perfil da
empresa e o sistema instala e configura os módulos daquele segmento.

O núcleo é aberto. A monetização vem de **hospedagem gerenciada (SaaS)** e de **módulos
avançados**.

Uma segunda intenção está registrada no `CLAUDE.md` e não deve ser esquecida na hora de
priorizar: o projeto também serve de **portfólio** para vagas no mercado internacional. Isso
às vezes empurra para o lado oposto do que o negócio pediria — profundidade de arquitetura
contra largura de funcionalidade. Quando as duas coisas brigarem, a escolha precisa ser
consciente, e não acidental.

## 2. Quem é o cliente, e qual é a dor

Pequeno e médio comércio brasileiro, preso em software de gestão legado: lento, difícil de
ler, penoso de operar. Fila de caixa parada esperando QR code, entrada de estoque digitada
item a item, papelada de conformidade ainda em talão carbonado.

Duas características do público viraram regra de produto, e não preferência de design:

- **Dono de loja frequentemente idoso** — daí o modo claro como padrão, o contraste
  calibrado e a proibição de preto puro sobre branco puro (`BRAND.md`).
- **Equipamento fraco** — PC antigo de caixa e celular ruim. Peso de bundle e consulta
  lenta são defeitos, não detalhes (regra 5 do `CLAUDE.md`).

## 3. Como se ganha dinheiro

| Fonte | O que é |
|---|---|
| Hospedagem gerenciada | O cliente não quer servidor; quer que funcione e que alguém responda quando não funcionar |
| Módulos avançados | O núcleo resolve; o que é específico e caro de fazer é pago |
| Serviço de implantação | Não está escrito em lugar nenhum, e é a receita que costuma aparecer primeiro neste mercado |

## 4. Onde o produto está — fato, não impressão

**O mecanismo está pronto; o conteúdo é que é fino.** É a constatação mais importante deste
documento, e ela é contraintuitiva de dentro do código, onde o que se vê é sempre o que
falta.

| A promessa | Estado em 29/10/2026 |
|---|---|
| Escolher o segmento e o sistema se configurar | **Existe.** Perfis, vitrine de aplicativos, instalar e desinstalar a qualquer momento, dependências resolvidas, dado-semente com identidade estável |
| Empresas isoladas umas das outras | **Existe.** Row Level Security no banco, provado por teste contra PostgreSQL real — não filtro na aplicação |
| Núcleo aberto, módulos instaláveis | **Existe.** 6 módulos com manifesto, migrações ramificadas por módulo, fronteira entre módulos cobrada por teste |
| Leveza | **Existe.** Bundle de ~350 kB, ~100 kB comprimido |
| Trilha de auditoria e LGPD técnica | **Existe.** Escrita nos fluxos de autenticação e contratação, e legível por tela |
| Verticais sobre a base | **Uma e meia.** Agro quase completo; "comércio" é genérico; distribuidora é uma pasta vazia |
| Validação em operação real | **Nenhuma.** A Fase 3 nunca começou |

Doze ADRs, 570 testes contra banco real, integração contínua verde. A parte difícil de
construir um Odoo — **ser** um Odoo — está feita.

## 5. O que falta para comercializar

Nada desta seção está no `ROADMAP.md`, porque o roadmap é de produto e isto é de operação.
Essa ausência é a razão de este documento existir.

### 5.1 Bloqueios de operação — a diferença entre "funciona" e "tem cliente"

| Bloqueio | O que há hoje | O que falta |
|---|---|---|
| **Cadastro de empresa** | `decko-admin bootstrap`, no terminal de quem mantém o sistema | Ninguém assina sozinho. Para SaaS isso é bloqueio absoluto. A ausência da rota é **deliberada** (`CONTRIBUTING.md`: não deixar cadastro aberto na internet), então o que falta é o fluxo de assinatura com dono responsável, não só a rota |
| **Implantação** | `infra/compose/` e `infra/observability/` estão vazios | O sistema nunca rodou fora da máquina de desenvolvimento. Falta servidor, domínio, TLS, processo de subida |
| **Backup e restauração** | Nada | Guardar CPF e dado fiscal de terceiro sem **restauração testada** é risco que não se corre. Backup que nunca foi restaurado não é backup |
| **Cobrança** | Nada | O módulo de plano recorrente que falta no roadmap é o mesmo que seria usado para cobrar do próprio cliente |
| **Suporte** | Nada | Canal, horário e o que acontece quando o caixa para às 18h de sábado |

### 5.2 Bloqueio de produto — só para o lado comércio

**Emissão fiscal (NFC-e/SAT).** Sem ela o PDV registra a venda e **não emite o cupom**:
nenhuma loja brasileira pode usá-lo como caixa. Exige certificado digital, homologação na
SEFAZ do estado, contingência e layout versionado — e é o item mais caro da lista inteira.

É este bloqueio, mais que qualquer outro, que decide **qual produto vai ao mercado
primeiro**.

### 5.3 Jurídico

CNPJ para faturar, contrato e termos de uso, política de privacidade, e os direitos do
titular pela LGPD: exportar e apagar os dados dele mediante pedido.

A parte técnica da LGPD está **à frente** da papelada: isolamento por RLS, trilha de
auditoria e cadastro que desativa em vez de apagar já existem.

### 5.4 O que não é bloqueio

Registrado para não consumir tempo antes da hora: as Fases 6 (OCR, LLM local, busca
semântica) e 7 (PWA, Android, desktop, observabilidade) **não bloqueiam a primeira venda**.
São ampliação, e ampliar antes de validar é como se constrói o produto errado com capricho.

## 6. Recomendação — opinião, não constatação

**O Agro vai ao mercado primeiro, e não o comércio.**

1. **Não precisa de emissão fiscal.** Contorna o item mais caro da seção 5.2.
2. **Tem cliente identificado**, e o documento regulatório já foi modelado a partir do
   formulário real em uso.
3. **O valor é dinheiro, não conveniência.** Prova defensável contra reclamação de deriva,
   e o relatório que o MAPA exige — hoje preenchido em talão de papel.

"ERP genérico para todo tipo de empresa" continua sendo a ideia certa. Mas é **destino, não
ponto de partida**: ninguém compra plataforma, compra solução de uma dor. A plataforma é o
que faz a segunda e a terceira dor custarem pouco — e é exatamente ela que já está
construída.

### O próximo passo não é código

**O Nathan usar por um mês, em operação real.** É a Fase 3 do roadmap, custa quase nada, e
responde se o produto está certo **antes** de haver gasto com hospedagem, CNPJ e suporte.

O que esse mês devolve, e nenhuma quantidade de código substitui: se o wizard aguenta o
campo, se o PDF passa no que o fiscal pede, quanto tempo economiza de verdade, e quanto
disso alguém pagaria.

---

## Perguntas em aberto — decisão do dono do projeto

1. **Vender como SaaS ou implantar na casa do cliente?** Muda tudo da seção 5.1. Implantação
   local adianta a primeira venda e cria custo de suporte que não escala.
2. **Preço.** Por empresa, por usuário, por módulo? Nenhuma hipótese foi testada.
3. **Agro é produto ou é o primeiro cliente?** Vender para uma operação de drone é diferente
   de vender para o setor.
4. **Até onde o núcleo fica aberto?** "Open Core" está decidido; a linha entre o que é
   aberto e o que é pago, não.
