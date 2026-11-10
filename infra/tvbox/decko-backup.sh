#!/bin/bash
# Copia de seguranca do banco do Decko.
#
# O destino fica na memoria interna, DE PROPOSITO: o banco mora no pendrive, e copia
# no mesmo dispositivo que os dados nao e copia de seguranca, e um segundo arquivo
# esperando a mesma falha.
#
# Isto ainda NAO e backup completo: nada sai desta maquina. Perda do box, roubo ou
# incendio levam dado e copia juntos. Ver docs/NEGOCIO.md, secao 5.1.
set -euo pipefail

DESTINO=/var/backups/decko
DIAS=14
CARIMBO=$(date +%Y%m%d-%H%M%S)
ARQUIVO="$DESTINO/decko-$CARIMBO.dump"

mkdir -p "$DESTINO"
chmod 700 "$DESTINO"

su postgres -c "pg_dump -Fc -d decko" > "$ARQUIVO"
chmod 600 "$ARQUIVO"

# Conferencia imediata: um dump que nao abre nao serve, e descobrir isso no dia da
# restauracao e tarde.
if ! su postgres -c "pg_restore --list '$ARQUIVO'" >/dev/null 2>&1; then
  echo "FALHOU: o dump $ARQUIVO nao e legivel" >&2
  exit 1
fi

find "$DESTINO" -name 'decko-*.dump' -mtime +$DIAS -delete
echo "ok: $ARQUIVO ($(du -h "$ARQUIVO" | cut -f1)), $(ls -1 "$DESTINO"/decko-*.dump | wc -l) copias guardadas"
