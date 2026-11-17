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

**O disco externo é medido antes de receber o banco.** A ideia original era simples —
PostgreSQL escreve o tempo todo e memória flash barata tem ciclo de gravação contado, então
o banco iria para o disco externo. Na primeira máquina real isso quase deu errado: o
pendrive de 58 GB não conseguiu escrever 32 MB em seis minutos e meio, menos de 80 kB/s,
contra 7,7 MB/s da memória interna. Com páginas de 8k, cada venda levaria segundos.

Então o script mede. Se o disco externo for rápido, o banco vai para lá. Se não for, o
banco fica na memória interna e o disco externo serve só para backup — o que, por acaso,
é melhor do que o plano original: dado e cópia passam a ficar em dispositivos físicos
diferentes, sem comprar nada.

**A aplicação e o `venv` ficam sempre na memória interna.** São milhares de arquivos
pequenos, e é esse padrão — não o volume — que um pendrive ruim não suporta. Instalar as
dependências no pendrive levou 26 minutos com a máquina em load 10; o gargalo eram
`usb-storage` e o diário do ext4, não rede nem memória.

**Só zram como swap.** Swap em disco externo lento não é rede de segurança: é o jeito de
travar a máquina inteira quando a memória apertar.

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

## Backup

`decko-backup.timer` roda às 3h30, guarda 14 dias no **disco externo** e recusa um dump que
não abra. Cópia diária é escrita sequencial de madrugada, então lentidão ali não atrapalha
ninguém — e o ponto é que os dados ficam num dispositivo e a cópia em outro.

`decko-testar-restauracao.sh` restaura a cópia mais recente num banco descartável e compara
tabelas e linhas, porque backup que nunca foi restaurado não é backup.

### Fazer a cópia sair da caixa

Disco que morre, o de cima resolve. Box que some, não: perda, roubo ou incêndio levavam
dado e cópia juntos, e desde 13/11/2026 há dado de cliente de verdade ali.

```bash
sudo ./configurar-backup-remoto.sh
```

O script instala o `rclone` e o `gpg`, sorteia a senha do cofre, conduz a autenticação na
conta de nuvem e, no fim, **faz a prova real**: envia uma cópia, baixa de volta, decifra e
abre como dump. Arquivo que sobe mas não volta a ser um dump legível é um backup que só
falha no dia em que for preciso.

Três decisões dentro dele:

**O que sai da caixa é cifrado; o que fica, não.** A cópia local mora num diretório 700 de
um disco que só sai de casa junto com o box; a remota atravessa a internet e dorme no
servidor de outra empresa. O dump tem CPF, CNPJ, cadastro de cliente e trilha de auditoria
— é a regra 2 do `CLAUDE.md`, e ela não termina quando o arquivo sai do banco.

**A senha não viaja junto.** Fica em `/etc/decko/backup.pass`, com 600, e **precisa de uma
cópia fora desta máquina**. Backup que carrega a própria chave não protege de quem leva o
backup; mas caixa perdida com a única cópia da senha transforma tudo o que está na nuvem em
arquivo embaralhado. O script para e exige confirmação escrita nesse ponto.

**Falha ao enviar derruba a execução; falta de configuração, não.** Sem
`/etc/decko/backup-remoto.env` o backup local continua e o log diz, em voz alta, que nada
saiu da máquina. Com ele configurado, qualquer erro no envio termina em erro — backup que
falha calado é pior do que backup que não existe, porque dá a impressão de existir.

### O que ainda não está coberto

O dump é só o banco. `/etc/decko/` — com as senhas do PostgreSQL, a chave de assinatura dos
tokens e a credencial do túnel — não sai daqui. Nenhum desses é insubstituível: numa caixa
nova eles se geram de novo, e o custo é que todo mundo precisa entrar outra vez. O que não
se recria é o banco, e esse agora tem cópia fora.

Restaurar continua sendo trabalho manual: instalar do zero, apontar o `decko-admin` e
subir o dump. Não há caixa reserva esperando.

## O túnel

É o túnel rápido da Cloudflare, sem conta: **a URL muda toda vez que o serviço reinicia**, e
a tela publicada leva essa URL embutida no pacote, então cada mudança pede um build novo.

Enquanto o box não for desligado, a URL se mantém. Para parar de depender disso é preciso
túnel nomeado, que exige um domínio dentro da Cloudflare.

### Túnel nomeado, quando existe domínio

O domínio `decko.app.br` foi registrado em 16/11/2026, e com ele o túnel deixa de sortear
endereço. O desenho é `decko.app.br` para a tela, na Vercel, e `api.decko.app.br` para a
API, por este túnel.

A ordem importa, e o motivo de cada passo é o mesmo: **nenhum deles pode quebrar o piloto
que já está no ar.**

1. **No registro.br**, troque os servidores de nome para os que a Cloudflare indicar ao
   adicionar a zona. Pode levar horas. Enquanto não propagar, o túnel rápido continua
   servindo — não mexa em mais nada até `dig NS decko.app.br` responder a Cloudflare.
2. **Na caixa**, com a zona já na Cloudflare:

   ```bash
   sudo ./configurar-tunel-nomeado.sh api.decko.app.br
   ```

   O script pede a autenticação na conta, cria o túnel, aponta o nome, instala a
   credencial em `/etc/decko/tunel` e troca o serviço. É seguro repetir.
3. **Ainda na caixa**, acrescente a origem nova ao CORS e reinicie a API. Esta variável
   guarda a origem **da tela**, não a do túnel, e vive em `/etc/decko/decko.env` — não na
   Vercel:

   ```
   DECKO_CORS_ORIGINS=https://decko.app.br,https://decko-web.vercel.app
   ```

   As duas juntas durante a virada: a tela antiga continua funcionando enquanto a nova não
   está publicada.
4. **Na Vercel**, acrescente o domínio `decko.app.br` ao projeto, aponte `VITE_API_URL`
   para `https://api.decko.app.br` e promova um build novo da `main`. Valor `VITE_` entra
   no pacote na montagem, então sem build novo nada muda.
5. **Só então desligue o túnel rápido**, na caixa:

   ```bash
   sudo systemctl disable --now decko-tunel
   ```

   Os dois ficam de pé até aqui, e é de propósito: a tela publicada leva a URL sorteada
   dentro do pacote, então desligar o rápido antes tira o cliente do ar até a Vercel
   montar de novo. E não há volta barata — parar e religar o rápido sorteia outra URL.

Por que a credencial exige usuário fixo: o túnel rápido roda com `DynamicUser` porque não
tem segredo nenhum: qualquer um levanta um e recebe uma URL sorteada. O nomeado guarda um
arquivo que vale o domínio inteiro, e por isso ele fica em `/etc/decko/tunel`, com dono
`decko` e permissão 600 — usuário sorteado a cada partida não conseguiria lê-lo, e não
deveria.

## Conferir que está de pé

```bash
# decko-tunel enquanto for o túnel rápido; decko-tunel-nomeado depois da virada.
systemctl is-active postgresql decko-api decko-tunel
curl -s localhost:8000/health
sudo /usr/local/sbin/decko-testar-restauracao.sh
```
