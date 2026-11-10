# Implantação num servidor ARM pequeno

O caso que originou esta pasta: um TV box Amlogic S912 com Armbian bookworm, **1,7 GB de
RAM**, 14 GB de memória interna e um pendrive de 58 GB. Serve para qualquer máquina ARM ou
x86 pequena rodando Debian 12.

```bash
sudo ./instalar.sh --disco /dev/sda1
```

Depois, a URL pública:

```bash
journalctl -u decko-tunel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
```

## O que o script decide, e por quê

**O banco mora no disco externo, não na memória interna.** PostgreSQL escreve o tempo todo
e memória flash de aparelho barato tem ciclo de gravação contado. O `--disco` é o que tira
essa escrita de cima do sistema. Sem ele dá para experimentar, mas não para deixar ligado.

**PostgreSQL 18 do repositório da PGDG, não o 15 do Debian.** O desenvolvimento e a esteira
rodam 18; piloto numa major diferente é divergência que só aparece em produção.

**Dois papéis de banco**, como manda a `docs/adr/0002-ambiente-de-desenvolvimento-nativo.md`:
`decko_owner` é dono do schema e só as migrações o usam; `decko_app` não é dono e **não tem
BYPASSRLS**, que é o que faz o Row Level Security valer para a aplicação. Superusuário aqui
tornaria o isolamento entre empresas decorativo.

**`synchronous_commit` fica ligado.** Dá para ganhar velocidade desligando, e o banco guarda
dado fiscal de terceiro: essa troca não se faz.

**A API escuta só em `127.0.0.1`.** Quem a expõe é o túnel. Nada do Decko fica aberto na
rede local por acidente.

**Senha nenhuma aparece na tela.** São geradas na própria máquina e vão para
`/etc/decko/decko.env`, com permissão 600 — regra 3 do `CLAUDE.md`.

## Backup, e o que ele ainda não cobre

`decko-backup.timer` roda às 3h30, guarda 14 dias em `/var/backups/decko` e recusa um dump
que não abra. O destino é a **memória interna**, de propósito: cópia no mesmo dispositivo
que os dados não é cópia de segurança.

`decko-testar-restauracao.sh` restaura a cópia mais recente num banco descartável e compara
tabelas e linhas, porque backup que nunca foi restaurado não é backup.

**O que falta:** nada sai da máquina. Perder o box leva dado e cópia juntos. Enquanto isso
não for resolvido, o item de backup do `docs/NEGOCIO.md` continua aberto.

## O túnel

É o túnel rápido da Cloudflare, sem conta: **a URL muda toda vez que o serviço reinicia**, e
a tela publicada leva essa URL embutida no pacote, então cada mudança pede um build novo.

Enquanto o box não for desligado, a URL se mantém. Para parar de depender disso é preciso
túnel nomeado, que exige um domínio dentro da Cloudflare.

## Conferir que está de pé

```bash
systemctl is-active postgresql decko-api decko-tunel
curl -s localhost:8000/health
sudo /usr/local/sbin/decko-testar-restauracao.sh
```
