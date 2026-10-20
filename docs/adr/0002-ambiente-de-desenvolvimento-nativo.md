# ADR 0002 — Ambiente de desenvolvimento nativo no Windows

- **Data:** 2026-10-19
- **Status:** aceito
- **Revisita:** quando entrar Redis/MinIO (Fase 2) ou IA local (Fase 6)

## Contexto

A máquina de desenvolvimento tem 16 GB de RAM, e havia preocupação de que containers
consumissem memória demais. O plano original previa Podman para toda a infraestrutura.

Medição dos componentes em repouso:

| Componente | RAM aproximada |
|---|---|
| PostgreSQL | 150 MB |
| Redis | 15 MB |
| MinIO | 180 MB |
| VM do WSL2 (base para containers no Windows) | 1–1,5 GB |
| Qdrant | 200 MB |
| Prometheus + Grafana + Jaeger | 800 MB |
| **Ollama + Qwen 2.5 7B** | **5–6 GB** |

## Decisão

Em desenvolvimento, serviços de infraestrutura rodam **nativos no Windows**. Nenhum
container por enquanto. Em produção, Linux com containers.

Instala-se apenas o que a fase corrente usa. A Fase 1 usa somente PostgreSQL.

## Motivo

O custo de memória dos serviços de dados é pequeno — os três juntos somam menos que uma
aba pesada de navegador. O peso real estava em dois lugares: a VM do WSL2, que no Windows
é condição para rodar container (tanto Podman quanto Docker), e o modelo de linguagem
local.

Como em desenvolvimento a aplicação roda nativa e não é containerizada, o container
traria a VM sem trazer benefício correspondente. Removê-lo economiza mais do que otimizar
qualquer serviço individual.

A escolha anterior por Podman em vez de Docker continua válida para produção, mas pelo
motivo correto: ausência de daemon e de restrição de licença comercial — não economia de
memória no Windows, onde os dois custam praticamente o mesmo.

## Consequências

- Desenvolvimento diverge da produção Linux. É o custo aceito desta decisão. Mitigações:
  acesso a serviço externo sempre atrás de interface padrão, e integração contínua em
  Linux antes do primeiro deploy.
- **Redis não tem build oficial para Windows.** Quando a Fase 2 precisar de cache, a
  escolha será entre Memurai (compatível, licença comercial em produção) e WSL. Decisão
  adiada até existir a necessidade.
- Armazenamento de objetos fica atrás da API S3, não acoplado ao MinIO. Isso mantém a
  troca por outro provedor como mudança de configuração.
- A LLM local da Fase 6 não cabe junto com o restante nesta máquina. Ou usa modelo menor,
  ou roda sob demanda, ou vai para outra máquina.

## Alternativas consideradas

**Podman com perfis no compose** — descartado por ora: resolveria o consumo (subindo só o
perfil necessário), mas ainda traria a VM do WSL2 sem ganho em desenvolvimento.

**Desenvolver dentro do WSL2** — descartado: o código está em disco Windows, e atravessar
a fronteira de sistema de arquivos é lento. Mudaria o fluxo de trabalho sem necessidade.
