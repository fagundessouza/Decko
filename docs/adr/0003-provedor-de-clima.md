# ADR 0003 — Open-Meteo como provedor de clima

- **Data:** 2026-10-19
- **Status:** aceito para o MVP
- **Revisita:** antes do primeiro cliente pagante, e se houver contestação judicial

## Contexto

O módulo agro precisa registrar temperatura, umidade relativa e velocidade do vento no
momento de cada aplicação. Duas características do uso real restringem a escolha:

1. **O relatório é preenchido depois do voo**, às vezes dias depois. Não basta "o tempo
   agora": é preciso o tempo daquela coordenada naquele horário.
2. **O registro tem função probatória.** Aplicar com vento fora da janela causa deriva
   sobre a lavoura vizinha, e disso nascem processos. Hoje o operador anota de memória,
   o que não constitui prova de nada.

## Decisão

Open-Meteo, consultando o endpoint de arquivo para datas com mais de seis dias e o de
previsão para as recentes. O endpoint usado fica gravado em cada leitura.

Cada leitura guarda, além do valor: origem (`api`, `manual` ou `sensor`), nome do conjunto
de dados, resposta íntegra do provedor, coordenada e horário.

## Motivo

Open-Meteo não exige chave de API, o que permite o sistema funcionar sem o cliente abrir
conta em serviço de terceiro antes de ver valor. Tem histórico por coordenada, que é o
requisito que elimina a maior parte das alternativas. Entrega as grandezas já em °C, % e
km/h — as mesmas unidades do formulário, sem conversão intermediária onde errar.

A divisão entre os dois endpoints existe porque o conjunto reanalisado é mais defensável,
mas só publica alguns dias depois. Registrar qual foi usado deixa o documento declarar a
própria procedência em vez de deixá-la implícita.

A consulta pede apenas o dia necessário. A janela ampla trazia 2232 horas, cerca de 80 KB,
para extrair uma leitura; o dia isolado traz 24 horas e 1,3 KB. O aparelho que faz essa
chamada costuma estar em rede ruim no meio da lavoura.

## Consequências

- **Risco aberto:** Open-Meteo é um modelo meteorológico, não uma estação no talhão. Em
  disputa judicial, a outra parte pode contestar a distância entre o ponto do modelo e o
  local da aplicação. O registro do payload e da coordenada mitiga, mas não elimina.
- O provedor está atrás de um `Protocol` e é injetado como dependência. Trocá-lo, ou somar
  uma estação física via a origem `sensor`, não toca o endpoint nem o modelo de dados.
- Sem cache. Cada captura é uma consulta externa. Com o volume de um operador isso é
  irrelevante; quando houver muitos clientes, o cache entra na frente do provedor.
- A origem `manual` continua existindo para quando não houver dado disponível — mas aí a
  leitura declara que foi informada à mão, que é exatamente a distinção que importa.

## Alternativas consideradas

**OpenWeatherMap, Weatherbit** — exigem chave de API, o que adiciona cadastro em terceiro
antes do primeiro uso e um segredo a gerenciar por instalação.

**Estação meteorológica no equipamento** — a prova mais forte possível, e provavelmente o
caminho futuro. Descartada agora porque exige hardware que a operação não tem, e porque o
formulário já é preenchido sem ela hoje: o ganho imediato está em eliminar a transcrição
manual, não em melhorar a precisão da medição.

**Nenhum provedor, só entrada manual** — é o que já existe no papel e não resolve nada.
