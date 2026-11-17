#!/bin/bash
# Confere se o Decko responde DE FORA, e nao so se o servico esta "active".
#
# Em 17/11/2026 o tunel ficou ativo pelo systemd e mudo para o mundo: a Cloudflare
# respondia 530 e ninguem conseguia entrar. Do lado de dentro estava tudo verde — API de
# pe, servico rodando, nenhuma unidade em falha. Processo vivo nao e servico funcionando,
# e era isso que faltava alguem notar.
#
# Entao a conferencia e pelo endereco publico, que e por onde o cliente chega.
set -uo pipefail

ENDERECO="${1:-https://api.decko.app.br/health}"
LOCAL="http://127.0.0.1:8000/health"
MARCA=/run/decko-vigia.falhas
# Duas falhas seguidas antes de mexer: uma sozinha e oscilacao de rede, e reiniciar a
# cada soluco deixaria o tunel subindo e descendo o dia inteiro.
LIMITE=2

if curl -fsS --max-time 20 "$ENDERECO" >/dev/null 2>&1; then
    rm -f "$MARCA"
    exit 0
fi

# A API local precisa estar de pe para a culpa ser do tunel. Se ela tambem estiver fora,
# quem resolve e o Restart=always da propria unidade — reiniciar o tunel nao adiantaria.
if ! curl -fsS --max-time 10 "$LOCAL" >/dev/null 2>&1; then
    echo "API local tambem nao responde; o tunel nao e o problema." >&2
    exit 0
fi

falhas=$(( $(cat "$MARCA" 2>/dev/null || echo 0) + 1 ))
echo "$falhas" > "$MARCA"

if [ "$falhas" -lt "$LIMITE" ]; then
    echo "$ENDERECO nao respondeu ($falhas de $LIMITE); aguardando a proxima conferencia." >&2
    exit 0
fi

echo "$ENDERECO fora em $falhas conferencias seguidas, com a API local de pe. Reiniciando o tunel." >&2
systemctl restart decko-tunel-nomeado
rm -f "$MARCA"
