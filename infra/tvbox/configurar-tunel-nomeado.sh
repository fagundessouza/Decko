#!/usr/bin/env bash
#
# Troca o tunel rapido por um tunel nomeado, com nome fixo no dominio do Decko.
#
# O tunel rapido sorteia uma URL nova a cada reinicializacao. Enquanto o piloto tinha um
# cliente so, isso custava um ajuste na Vercel; com cliente de verdade entrando todo dia,
# custa o sistema fora do ar em silencio, com cara de "nao consigo entrar".
#
# Roda na propria caixa, como root, DEPOIS de o dominio estar na Cloudflare:
#
#     sudo ./configurar-tunel-nomeado.sh api.decko.app.br
#
# E seguro repetir: cada passo confere antes de fazer.

set -euo pipefail

HOSTNAME_API="${1:-}"
NOME_TUNEL="${NOME_TUNEL:-decko}"
DESTINO="/etc/decko/tunel"
UNIDADE_RAPIDA="decko-tunel.service"
UNIDADE_NOMEADA="decko-tunel-nomeado.service"
AQUI="$(cd "$(dirname "$0")" && pwd)"

passo() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
erro() { printf '\033[1;31merro: %s\033[0m\n' "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || erro "rode com sudo."
[ -n "$HOSTNAME_API" ] || erro "informe o nome da API. Exemplo: $0 api.decko.app.br"
command -v cloudflared >/dev/null || erro "cloudflared nao esta instalado."
id decko >/dev/null 2>&1 || erro "o usuario 'decko' nao existe: rode o instalar.sh antes."

# ------------------------------------------------------------------ 1. credencial da conta

passo "conta da Cloudflare"
if [ -f /root/.cloudflared/cert.pem ]; then
    echo "ja autenticado (/root/.cloudflared/cert.pem)."
else
    echo "Vai aparecer uma URL. Abra no navegador, entre na sua conta e escolha o dominio."
    cloudflared tunnel login
    [ -f /root/.cloudflared/cert.pem ] || erro "a autenticacao nao completou."
fi

# ------------------------------------------------------------------ 2. o tunel

passo "tunel '$NOME_TUNEL'"
if cloudflared tunnel list --output json | grep -q "\"name\":\"$NOME_TUNEL\""; then
    echo "ja existe."
else
    cloudflared tunnel create "$NOME_TUNEL"
fi

# Pergunta o id deste tunel pelo nome. Varrer a lista pegaria o primeiro de todos,
# que nem sempre e o nosso.
UUID="$(cloudflared tunnel info "$NOME_TUNEL" --output json | tr ',' '\n' \
    | grep -m1 '"id"' | cut -d'"' -f4)"
[ -n "$UUID" ] || erro "nao consegui descobrir o id do tunel."
echo "id: $UUID"

CREDENCIAL="/root/.cloudflared/$UUID.json"
[ -f "$CREDENCIAL" ] || erro "credencial $CREDENCIAL nao encontrada."

# ------------------------------------------------------------------ 3. o nome no dominio

passo "apontando $HOSTNAME_API para o tunel"
# Cria o CNAME para <uuid>.cfargotunnel.com na zona. So resolve dentro da Cloudflare, e e
# por isso que o dominio precisa estar la — no registro.br isto nao existe.
cloudflared tunnel route dns "$NOME_TUNEL" "$HOSTNAME_API" || {
    echo "a rota ja existia ou a zona recusou; conferindo adiante."
}

# ------------------------------------------------------------------ 4. arquivos na caixa

passo "configuracao em $DESTINO"
install -d -m 750 -o decko -g decko "$DESTINO"
install -m 600 -o decko -g decko "$CREDENCIAL" "$DESTINO/credencial.json"

cat > "$DESTINO/config.yml" <<CONFIG
# Gerado por configurar-tunel-nomeado.sh. A API escuta so em 127.0.0.1: quem a expoe e
# este tunel, e nada mais do Decko fica aberto na rede local.
tunnel: $UUID
credentials-file: $DESTINO/credencial.json

ingress:
  - hostname: $HOSTNAME_API
    service: http://127.0.0.1:8000
  # Qualquer outro nome que chegue por este tunel morre aqui.
  - service: http_status:404
CONFIG
chown decko:decko "$DESTINO/config.yml"
chmod 640 "$DESTINO/config.yml"

install -m 644 "$AQUI/$UNIDADE_NOMEADA" /etc/systemd/system/
systemctl daemon-reload

# ------------------------------------------------------------------ 5. subir, sem derrubar

passo "subindo o tunel nomeado ao lado do rapido"
# O rapido continua de pe de proposito. A tela publicada ainda leva a URL sorteada dentro
# do pacote, e derrubar o tunel agora tiraria o cliente do ar ate a Vercel montar de novo.
# Pior: parar e religar o rapido sorteia outra URL, entao nao ha volta barata.
#
# Os dois convivem — sao processos distintos, nenhum escuta porta local. O rapido sai no
# fim, quando a tela ja estiver no dominio novo.
systemctl enable --now "$UNIDADE_NOMEADA"

sleep 8
systemctl is-active --quiet "$UNIDADE_NOMEADA" || {
    journalctl -u "$UNIDADE_NOMEADA" -n 20 --no-pager
    erro "o tunel nomeado nao subiu."
}

passo "conferindo"
echo -n "local:  "; curl -fsS --max-time 10 http://127.0.0.1:8000/health >/dev/null \
    && echo "ok" || echo "FALHOU"
echo -n "pelo nome: "
if curl -fsS --max-time 25 "https://$HOSTNAME_API/health" >/dev/null; then
    echo "ok"
else
    echo "ainda nao responde — o DNS pode levar alguns minutos para propagar."
fi

cat <<FIM

Pronto. Falta o que mora fora desta caixa:

  1. Na Vercel, DECKO_CORS_ORIGINS nao e la — e aqui. Acrescente a origem da tela em
     /etc/decko/decko.env e reinicie a API:

       DECKO_CORS_ORIGINS=https://decko.app.br,https://decko-web.vercel.app
       systemctl restart decko-api

  2. Na Vercel, acrescente o dominio da tela ao projeto, aponte VITE_API_URL para
     https://$HOSTNAME_API e promova um build novo da main — valor VITE_ entra no pacote
     na montagem, nao em tempo de execucao.

  3. So depois que a tela nova estiver no ar e entrando, desligue o tunel rapido:

       systemctl disable --now $UNIDADE_RAPIDA

     Ate la os dois ficam de pe. O rapido ainda e quem serve a tela publicada.

FIM
