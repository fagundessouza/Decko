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

   **Quando o site de prospecção for publicado** em `web.decko.app.br` (roteiro em
   `apps/site/README.md`), esta variável precisa das duas origens finais:

   ```
   DECKO_CORS_ORIGINS=https://decko.app.br,https://web.decko.app.br
   ```

   A raiz continua na lista porque é de lá que o sistema chama. O subdomínio entra porque o
   formulário de contato da landing chama a API do próprio navegador do visitante — e, sem
   ele, o formulário falha em silêncio.
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

## Queda de energia

Em 17/11/2026 um pico derrubou a caixa **duas vezes** na mesma madrugada, às 01h16 e às
02h16. Ela voltou sozinha nas duas, com banco íntegro, e o backup das 3h30 rodou depois —
é o comportamento desejado, e está conferido, não suposto.

O que o `systemd` garante: a máquina liga, o PostgreSQL sobe pelo `postgresql.service`, a
API espera por ele (`Requires=`) e o túnel sobe em seguida. Os três reiniciam sozinhos se
caírem, e desde esta data com `StartLimitIntervalSec=0` — sem isso, o padrão do systemd
desiste depois de cinco partidas em dez segundos e deixa a unidade morta até alguém mandar
subir à mão. Numa caixa atrás de uma tomada, "alguém" não existe.

O que **não** está protegido, e é decisão em aberto: o sistema de arquivos está montado com
`commit=600,data=writeback`, que é o ajuste do Armbian para poupar cartão. São dez minutos
de metadados em memória e gravação de dado fora de ordem — o que se perde numa queda. O
banco não corre esse risco, porque o PostgreSQL faz `fsync` do WAL por conta própria e o
`synchronous_commit` está ligado; o que pode se perder é arquivo comum escrito nos minutos
anteriores. Como a escrita medida é de ~225 MiB/dia, o desgaste que esse ajuste evita é
pequeno perto do que ele custa em queda de luz.

## O que liga sozinho

É o equivalente aos "aplicativos de inicialização" do Windows, e no systemd ele se chama
`enable`. Tudo o que o Decko precisa já está armado:

```bash
systemctl is-enabled postgresql decko-api decko-tunel-nomeado decko-backup.timer decko-vigia.timer
```

As cinco respondem `enabled`. Na prática: a máquina liga, o PostgreSQL sobe, a API espera
por ele (`Requires=`), o túnel sobe em seguida e os dois temporizadores entram. Nada disso
depende de alguém logar na caixa.

### Processo vivo não é serviço funcionando

Em 17/11/2026 o túnel ficou `active` para o systemd e **mudo para o mundo**: a Cloudflare
respondia 530 e ninguém conseguia entrar. Do lado de dentro estava tudo verde — API de pé,
unidade rodando, nenhuma falha. A causa era o QUIC: `cloudflared` usa UDP/7844 por padrão,
e link residencial derruba UDP com frequência. O log repetia `failed to dial to edge with
quic` nas quatro conexões. Com `protocol: http2` no `config.yml`, as quatro registraram em
segundos.

Como `enable` não cobre esse caso — a unidade estava ativa —, entrou o
`decko-vigia.timer`: de cinco em cinco minutos ele pergunta pelo **endereço público**, que
é por onde o cliente chega. Duas falhas seguidas, com a API local respondendo, e ele
reinicia o túnel. A API local precisa estar de pé para a culpa ser do túnel; se ela também
estiver fora, quem resolve é o `Restart=always` dela, e reiniciar o túnel não adiantaria.
Duas falhas, e não uma, porque reiniciar a cada soluço de rede deixaria o túnel subindo e
descendo o dia inteiro.

## Conferir que está de pé

```bash
# decko-tunel enquanto for o túnel rápido; decko-tunel-nomeado depois da virada.
systemctl is-active postgresql decko-api decko-tunel
curl -s localhost:8000/health
sudo /usr/local/sbin/decko-testar-restauracao.sh
```
