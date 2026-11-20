# Discovery — Gestão da fazenda (produtor rural)

**Pedido:** Lucas Fagundes Souza, em 20/11/2026. A mãe dele vai assumir a administração da
roça do avô e pediu um sistema para tocar a propriedade inteira.
**Usuária real:** a mãe do dono do projeto — **disponível para entrevista**, o que torna
este o segundo módulo do Decko com usuário de verdade do lado, como foi a pulverização com
o talão da AgroDrone.
**Status:** levantamento aberto. **Nada aqui é requisito validado ainda.** As perguntas da
seção 8 precisam ser respondidas antes de qualquer migração.

> Regra 6 do `CLAUDE.md`: o domínio é regulado. O que este documento afirma sobre norma
> está marcado como **a confirmar** justamente porque a redação muda por estado e por ano,
> e errar aqui não é defeito de software — é multa no nome de quem usa.

---

## 1. A descoberta que muda tudo: é o outro lado do balcão

O módulo `agro` de hoje foi construído para a **AgroDrone**, que é **prestadora de
serviço**: ela aplica na lavoura dos outros, e o produto que ela entrega é a aplicação mais
o documento do MAPA. Está escrito no modelo:

- `agro_client` é o **contratante** do serviço.
- `agro_property` pendura em `client_id` — toda propriedade pertence a um cliente.
- O planejamento operacional é a ordem de serviço daquela aplicação, e o relatório mensal é
  obrigação da empresa aeroagrícola.

A fazenda da mãe é o **produtor rural**: ela é dona da terra. Nesse mundo:

- A propriedade **é da própria empresa**, não de um cliente. Pendurar a fazenda dela num
  registro de "cliente" seria mentir no modelo para reaproveitar uma tabela.
- O cliente **existe**, mas é quem **compra a produção** — a cerealista, o frigorífico, o
  comprador do boi. É papel de comprador, não de contratante.
- A aplicação de defensivo deixa de ser receita e vira **custo**, lançado contra um talhão.

Isto não é detalhe de nomenclatura: é quem é o dono do dado e para que serve o documento.
A decisão de como acomodar os dois lados está no ADR 0023.

**O caso dela acumula os dois papéis.** Se a fazenda contratar pulverização de terceiro,
ela é contratante; se tiver drone ou autopropelido próprio, ela é executora da própria
aplicação — e aí precisa do receituário e do registro igual, porque a exigência segue o
uso do defensivo, não o CNPJ de quem pulveriza (**a confirmar**, seção 7).

---

## 2. O que o Decko já tem e serve sem mudar nada

Esta é a resposta direta ao "se tiver algo que fique redundante que dê pra ser utilizado".
A fazenda **não precisa de um controle de estoque novo**:

| O que a fazenda precisa | O que já existe | Módulo |
|---|---|---|
| Entrada e saída de soja, milho, semente, adubo | Razão de movimentação com origem: o saldo é a soma do que aconteceu | `comercial` |
| Saca, tonelada, big bag, frasco, caixa | Embalagem em árvore, com conversão para a unidade base | `comercial` |
| Lote e validade de vacina, semente tratada, defensivo | Lote com saldo e aviso de vencimento | `comercial` |
| Entrada da nota do fornecedor de insumo | Cadastro de produto automatizado pela nota | `compras` |
| Quem compra a produção | Cadastro com CPF/CNPJ conferido | `clientes` |
| Para onde o dinheiro entrou | Conta de recebimento | `financeiro` |
| Defensivo com classe toxicológica e registro MAPA | Cadastro de produto do agro | `agro` |
| Receituário agronômico com CREA | Receituário | `agro` |
| Chuva e condição do tempo com prova | Leitura meteorológica com payload bruto guardado | `agro` |
| Horímetro de máquina | Horímetro de aeronave, por aplicação | `agro` |
| Quem pode ver e fazer o quê, com trilha | Permissões, papéis, auditoria | `core` |
| Ativar o conjunto de módulos pelo ramo | Perfil de segmento | plataforma |

**Diesel no tanque é estoque.** Peça de reposição é estoque. Vacina na geladeira é estoque
com lote e validade. Soja no silo é estoque com lote. Nada disso pede motor novo: pede
**razão de movimentação com motivo "consumo interno"** em vez de venda, e um centro de
custo para dizer contra qual talhão ou qual máquina o consumo foi lançado.

## 3. O que já é redundante hoje, antes mesmo da fazenda entrar

Três duplicações **que já existem** no repositório e que a gestão rural vai agravar se
ninguém decidir:

1. **`agro_client` × `clientes.cliente`.** Duas tabelas de cliente, com nome, CPF/CNPJ,
   telefone e e-mail. O `agro` nasceu antes do módulo `clientes` e ficou com o seu.
2. **`agro_product` × `comercial.produto`.** O defensivo existe nos dois mundos: no `agro`
   porque precisa de classe toxicológica e registro no MAPA, no `comercial` porque é
   estoque que entra e sai. Hoje o `agro` dá baixa chamando o serviço do `comercial` — mas
   o cadastro é duplo, e nada garante que apontam para a mesma coisa.
3. **`agro_property` presa a `client_id`.** Não há como cadastrar a fazenda da própria
   empresa sem inventar um cliente que é ela mesma.

As três são decisão de arquitetura, não de implementação, e estão no ADR 0023.

---

## 4. O escopo pedido, traduzido

O pedido foi "tudo... tudo mesmo". Traduzido para domínios, com o que cada um guarda:

### 4.1 A terra
Propriedade (a fazenda em si), **talhão / gleba** para lavoura, **piquete / retiro** para
pasto, área em hectares, e a safra como ciclo. Chuva por talhão. É a espinha de que lavoura
e pecuária penduram.

### 4.2 Lavoura
Cultura e cultivar, data de plantio, população e espaçamento, tratos (aplicações, adubação
de cobertura), colheita com produtividade em sacas por hectare, umidade e impureza. O
destino da colheita: silo próprio, armazém de terceiro, cooperativa, venda direta.

### 4.3 Rebanho
Cabeças por categoria (bezerro, novilha, garrote, boi, vaca, matriz, touro), identificação
individual por brinco ou controle por lote, nascimento, morte, compra, venda, abate.
Pesagem e ganho de peso. Reprodução: cobertura ou inseminação, diagnóstico de gestação,
parto. Piquete onde o lote está, e por quanto tempo.

### 4.4 Sanidade animal
Vacina aplicada, em qual lote ou animal, por quem, com qual produto e **qual lote do
frasco** — é o lote que a fiscalização pede. Vermifugação, medicação, carência antes do
abate. Calendário do que vence.

### 4.5 Frota e máquinas
Trator, colheitadeira, pulverizador autopropelido, caminhão, drone, aeronave agrícola,
implemento (grade, plantadeira, distribuidor). Horímetro para quem trabalha por hora,
odômetro para quem roda estrada. Manutenção preventiva por hora ou quilômetro, corretiva
com ordem de serviço, e as peças que entraram nela.

### 4.6 Custo
Esta é a pergunta que o produtor faz no fim da safra e que planilha nenhuma responde
direito: **quanto custou o hectare, e quanto custou a arroba.** Para responder, todo
lançamento — insumo consumido, hora de máquina, diária de gente, combustível — precisa
dizer contra **qual talhão ou qual lote de gado** foi. Sem centro de custo, o sistema vira
um caderno caro.

---

## 5. O que o pedido não citou e a área exige

O dono do projeto pediu explicitamente que esta parte fosse preenchida por quem conhece a
área. Cada item abaixo é coisa que aparece na fazenda e que não estava na lista:

| # | O que falta | Por que dói sem isso |
|---|---|---|
| 1 | **Pluviômetro: registro de chuva por talhão** | É o dado que decide plantio, aplicação e colheita. Hoje mora num caderno na cozinha, e some |
| 2 | **Combustível: tanque na fazenda, abastecimento por máquina** | Diesel é dos maiores custos e o mais fácil de sumir. Sem consumo por máquina (L/h) não há como notar desvio |
| 3 | **GTA — Guia de Trânsito Animal** | Nenhum animal sai da fazenda sem ela. Controlar rebanho sem GTA é controlar metade (**a confirmar**) |
| 4 | **Declaração de rebanho à agência estadual** | Obrigação periódica; o saldo declarado tem de bater com o do sistema (**a confirmar**) |
| 5 | **Carência de medicamento antes do abate** | Mandar para o abate dentro da carência é problema sanitário e comercial, e é erro de calendário |
| 6 | **Arrendamento, parceria e sucessão** | A roça é do avô. Quem é o titular da terra, quem é o produtor e quem assina muda a obrigação fiscal inteira |
| 7 | **CAR, reserva legal e APP** | Área produtiva não é a área total da matrícula. Lançar custo por hectare sobre a área errada erra tudo |
| 8 | **Pessoas: diária, empreita, EPI (NR-31)** | Não é folha de pagamento — é o controle operacional de quem trabalhou, quanto e com qual equipamento de proteção (**a confirmar**) |
| 9 | **Livro Caixa do Produtor Rural / LCDPR** | O produtor presta contas por regime de caixa; o sistema que não exporta isso joga trabalho de volta no contador (**a confirmar**) |
| 10 | **Nota Fiscal do Produtor** | A venda de grão e de boi sai com nota; o Decko ainda não emite nota nenhuma |
| 11 | **Contrato de venda e barter** | Soja vendida a termo, ou trocada por insumo, é compromisso de entrega futura — não é venda à vista |
| 12 | **Contas a pagar** | O `financeiro` hoje só sabe para onde o dinheiro **entra**. A fazenda é, em dinheiro, quase só saída |
| 13 | **Pastagem: lotação e rotação de piquete** | Lotação errada degrada pasto, e degradação de pasto é prejuízo que aparece dois anos depois |
| 14 | **Irrigação, se houver pivô** | Hora de pivô é energia, e energia é custo por hectare |
| 15 | **Benfeitoria e cerca** | Manutenção de cerca e curral some do custo porque ninguém lança |

**O item 12 é o maior buraco, e não é só do agro.** "Contas a pagar" falta para todas as
verticais; a fazenda só é a primeira a tornar isso impossível de ignorar.

---

## 6. Pulverização: três equipamentos, não um

O dono do projeto notou certo: pulveriza-se por **drone**, por **autopropelido terrestre** e
por **avião agrícola**. O modelo de hoje só comporta o terceiro e meio:

- `agro_aircraft` guarda `prefixo`, que é matrícula de aeronave. Um autopropelido não tem
  prefixo; um trator não tem.
- `agro_pilot` guarda `canac`, que é o registro do piloto na ANAC. Quem opera autopropelido
  não tem CANAC.
- `EquipamentoTipo` — barras e bicos, eletrostático, sólidos, atomizadores — **não é** o
  veículo: é o sistema de dispersão, e veio do talão em uso. Ele continua valendo para os
  três.

Então falta a dimensão **veículo aplicador**, e ela é exatamente a mesma coisa que a frota
precisa cadastrar. Drone, autopropelido, avião e trator são máquinas com horímetro e
manutenção; o que muda é qual documento cada uma exige.

**O que muda por veículo, e precisa ser confirmado (seção 7):** a aviação agrícola é
regulada como atividade, com empresa, aeronave e piloto registrados, e com o relatório
mensal ao MAPA. A aplicação terrestre na própria lavoura não tem o mesmo relatório — mas
tem receituário agronômico e guarda do registro da aplicação.

---

## 7. O que é regulado e **não pode ser inventado**

Lista do que precisa de fonte antes de virar campo no banco. Nenhum destes itens deve ser
implementado a partir deste documento:

1. **Vacinação obrigatória do rebanho.** Quais doenças, qual faixa etária, qual periodicidade
   e qual o prazo de comprovação — e isso mudou nos últimos anos e varia por estado.
2. **GTA:** o que exige, quem emite, quanto tempo vale, e o que precisa estar guardado.
3. **Declaração de rebanho:** prazo e conteúdo, por estado.
4. **Carência de medicamento:** vem da bula de cada produto, não de uma regra geral.
5. **Receituário agronômico na aplicação em lavoura própria:** o que exatamente obriga.
6. **Aviação agrícola:** Decreto 86.765/1981 e Portaria MAPA 298/2021 já estão levantados em
   `docs/discovery/agro-normas-mapa.md`. Aplicação terrestre **não** está.
7. **LCDPR:** quem é obrigado, a partir de qual receita, e o leiaute do arquivo.
8. **Nota Fiscal do Produtor:** modelo, quem emite, e se o estado exige emissão própria.
9. **NR-31:** o que precisa estar registrado sobre EPI, treinamento e exame.
10. **CAR e reserva legal:** o que o sistema pode afirmar sobre área, e o que ele só deve guardar.

---

## 8. Perguntas para a entrevista

Para a mãe, antes de qualquer linha de código. Em ordem de impacto no modelo — as quatro
primeiras mudam o desenho, as outras mudam a fatia.

**Sobre a propriedade e a titularidade**
1. A fazenda é uma só, ou são áreas separadas? Têm nomes diferentes no dia a dia?
2. A terra está no nome do avô. Quem vai ser o **produtor** — quem emite nota e presta
   contas? Existe arrendamento ou parceria no meio?
3. Quantos hectares no total, e quanto disso é lavoura, pasto e reserva?
4. Quem mais vai usar o sistema além dela? Tem gerente, capataz, tratorista?

**Sobre o que ela tem hoje**
5. Como ela controla hoje? Caderno, planilha, memória? **Traga o caderno** — é a fonte
   melhor que qualquer pergunta minha, do mesmo jeito que o talão foi para a pulverização.
6. Tem contador? O que ele pede para ela todo mês?

**Sobre o rebanho**
7. Quantas cabeças, e de que categorias? Cria, recria, engorda, leite?
8. Os animais têm brinco com número, ou o controle é por lote?
9. Como ela sabe hoje quais animais já tomaram qual vacina?
10. Vende para frigorífico, para outro produtor, em leilão?

**Sobre a lavoura**
11. Quais culturas, e quantas safras por ano? Soja na primeira, milho na segunda?
12. A área é dividida em talhões com nome? Como ela chama cada pedaço?
13. A colheita vai para silo próprio, cooperativa ou armazém de terceiro?
14. Vende na hora ou guarda para vender depois? Já fez barter — troca de insumo por grão?

**Sobre máquinas**
15. Quais máquinas tem? Trator, colheitadeira, pulverizador, caminhão?
16. A manutenção é por horímetro ou "quando dá problema"?
17. Tem tanque de diesel na fazenda? Como ela sabe quanto cada máquina gastou?

**Sobre o dinheiro**
18. O que ela mais quer saber no fim do mês? E no fim da safra?
19. Hoje ela consegue dizer quanto custou um hectare de soja? E uma arroba de boi?
20. Quais contas vencem todo mês sem falta — energia, arrendamento, financiamento?

**Sobre pulverização**
21. A aplicação é feita por ela, ou contrata alguém?
22. Se contrata: ela recebe algum papel do aplicador? Guarda?
23. Se faz: com qual equipamento — drone, autopropelido, costal?

---

## 9. O que **não** entra

- **Folha de pagamento, ponto e eSocial.** Está fora do Decko inteiro, e a fazenda não muda
  isso. Diária e empreita são controle operacional, que é outra coisa.
- **Contabilidade.** O sistema entrega ao contador o que aconteceu; não escritura.
- **Emissão fiscal.** Não existe em módulo nenhum ainda — ver `docs/adr/0018`.
- **Previsão de safra, mercado futuro, cotação.** É outro produto.
- **Mapa e agricultura de precisão por imagem de satélite.** Fora de escopo por ora.

---

## 10. Por que isto é bom para o produto, e não só para a mãe

Vale registrar, porque muda a prioridade: **o produtor rural é um segmento maior que o
prestador de pulverização**, e a fazenda exercita três coisas que o Decko precisa de
qualquer jeito —

1. **Contas a pagar e centro de custo**, que faltam para todas as verticais.
2. **Frota e manutenção**, que a distribuidora de bebidas também vai pedir, e que a página
   dela já admite não existir.
3. **Consumo interno de estoque**, que hoje só sabe sair por venda.

Nenhuma das três é código jogado fora se a fazenda mudar de ideia.
