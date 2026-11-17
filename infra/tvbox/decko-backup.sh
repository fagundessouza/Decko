#!/bin/bash
# Copia de seguranca do banco do Decko.
#
# O banco mora na memoria interna (/var/lib/postgresql, no cartao) e a copia vai para o
# disco externo montado em /srv/decko. Sao dispositivos fisicos diferentes de proposito:
# copia no mesmo dispositivo que os dados nao e copia de seguranca, e um segundo arquivo
# esperando a mesma falha.
#
# Desde 17/11/2026 a copia tambem SAI da maquina, cifrada, quando
# /etc/decko/backup-remoto.env existir. Sem isso, perda do box, roubo ou incendio levam
# dado e copia juntos — ver docs/NEGOCIO.md, secao 5.1, e o README desta pasta.
set -euo pipefail

DESTINO=/srv/decko/backups
DIAS=14
DIAS_REMOTO=${DIAS_REMOTO:-60}
CONFIG_REMOTO=/etc/decko/backup-remoto.env
CARIMBO=$(date +%Y%m%d-%H%M%S)
ARQUIVO="$DESTINO/decko-$CARIMBO.dump"

mkdir -p "$DESTINO"
chmod 700 "$DESTINO"

su postgres -c "pg_dump -Fc -d decko" > "$ARQUIVO"
chmod 600 "$ARQUIVO"

# Conferencia imediata: um dump que nao abre nao serve, e descobrir isso no dia da
# restauracao e tarde.
# Como root, e nao como postgres: o diretorio e 700 e postgres nao le nada aqui.
# Antes isto dizia "nao e legivel" quando o problema era permissao — mensagem errada
# que mandaria procurar corrupcao onde nao havia.
if ! pg_restore --list "$ARQUIVO" >/dev/null 2>&1; then
  echo "FALHOU: o dump $ARQUIVO nao e legivel" >&2
  exit 1
fi

find "$DESTINO" -name 'decko-*.dump' -mtime +$DIAS -delete
echo "ok: $ARQUIVO ($(du -h "$ARQUIVO" | cut -f1)), $(ls -1 "$DESTINO"/decko-*.dump | wc -l) copias guardadas"

# ------------------------------------------------------------------ copia fora de casa

if [ ! -f "$CONFIG_REMOTO" ]; then
  echo "AVISO: nenhuma copia saiu desta maquina. Rode configurar-backup-remoto.sh." >&2
  exit 0
fi

# shellcheck source=/dev/null
. "$CONFIG_REMOTO"
: "${RCLONE_REMOTO:?defina RCLONE_REMOTO em $CONFIG_REMOTO}"
: "${SENHA_ARQUIVO:?defina SENHA_ARQUIVO em $CONFIG_REMOTO}"
: "${RCLONE_CONFIG:?defina RCLONE_CONFIG em $CONFIG_REMOTO}"
export RCLONE_CONFIG

CIFRADO="$ARQUIVO.gpg"
# O cifrado nasce e morre aqui dentro: a copia local fica em claro, num diretorio 700 de
# um disco que so sai da casa junto com o box. O que atravessa a internet e dorme no
# servidor de outra empresa e outra conversa — o dump tem CPF, CNPJ e cadastro de cliente
# (regra 2 do CLAUDE.md).
trap 'rm -f "$CIFRADO"' EXIT

gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
    --passphrase-file "$SENHA_ARQUIVO" --pinentry-mode loopback \
    -o "$CIFRADO" "$ARQUIVO"
chmod 600 "$CIFRADO"

# Confere o que vai subir, e nao o que ficou: decifra e abre. Cifrar um arquivo bom e
# subir um ruim e exatamente o tipo de falha que so aparece no dia da restauracao.
if ! gpg --batch --quiet --decrypt --passphrase-file "$SENHA_ARQUIVO" \
        --pinentry-mode loopback "$CIFRADO" 2>/dev/null | pg_restore --list >/dev/null 2>&1; then
  echo "FALHOU: o arquivo cifrado nao volta a ser um dump legivel" >&2
  exit 1
fi

if ! rclone copy --no-traverse --retries 3 "$CIFRADO" "$RCLONE_REMOTO" 2>&1; then
  echo "FALHOU: a copia nao subiu para $RCLONE_REMOTO" >&2
  exit 1
fi

# Confere que chegou, pelo tamanho. rclone copy ja verifica soma, mas quem le o log
# precisa ver a confirmacao de que existe la, e nao so que o comando saiu com zero.
if ! rclone lsf "$RCLONE_REMOTO/$(basename "$CIFRADO")" >/dev/null 2>&1; then
  echo "FALHOU: subiu sem erro, mas o arquivo nao aparece em $RCLONE_REMOTO" >&2
  exit 1
fi

rclone delete --min-age "${DIAS_REMOTO}d" "$RCLONE_REMOTO" 2>/dev/null || true

echo "ok: $(basename "$CIFRADO") no destino remoto, $(rclone lsf "$RCLONE_REMOTO" | wc -l) copias la"
