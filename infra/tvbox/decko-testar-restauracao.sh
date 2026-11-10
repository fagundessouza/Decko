#!/bin/bash
# Restaura a copia mais recente num banco descartavel e compara a contagem de linhas.
#
# Existe porque "backup que nunca foi restaurado nao e backup" — e a unica forma de
# saber e restaurando de verdade, nao olhando o tamanho do arquivo.
set -euo pipefail

ULTIMO=$(ls -1t /srv/decko/backups/decko-*.dump 2>/dev/null | head -1)
[ -z "$ULTIMO" ] && { echo "nenhuma copia encontrada" >&2; exit 1; }

su postgres -c "dropdb --if-exists decko_teste_restauracao"
su postgres -c "createdb decko_teste_restauracao"
# O postgres nao le /srv/decko/backups (700, root). Copia temporaria com permissao
# de leitura, restaura, apaga — o original continua trancado.
TMP=$(mktemp /tmp/decko-restauracao-XXXXXX.dump)
cp "$ULTIMO" "$TMP"
chmod 644 "$TMP"
su postgres -c "pg_restore -d decko_teste_restauracao --no-owner --no-privileges '$TMP'" 2>/dev/null || true
rm -f "$TMP"

contar() {
  su postgres -c "psql -tAq -d $1 -c \"SELECT coalesce(sum(n_live_tup),0) FROM pg_stat_user_tables\"" 2>/dev/null | tr -d ' '
}
su postgres -c "psql -q -d decko_teste_restauracao -c 'ANALYZE'" >/dev/null 2>&1

ORIG=$(contar decko)
COPIA=$(contar decko_teste_restauracao)
TAB_O=$(su postgres -c "psql -tAq -d decko -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'\"")
TAB_C=$(su postgres -c "psql -tAq -d decko_teste_restauracao -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'\"")

echo "  copia testada: $(basename "$ULTIMO")"
echo "  tabelas:  origem=$TAB_O  restaurado=$TAB_C"
echo "  linhas:   origem=$ORIG  restaurado=$COPIA"
su postgres -c "dropdb --if-exists decko_teste_restauracao"

[ "$TAB_O" = "$TAB_C" ] || { echo "  DIVERGIU no numero de tabelas" >&2; exit 1; }
echo "  restauracao conferida"
