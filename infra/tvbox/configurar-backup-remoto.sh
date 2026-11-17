#!/usr/bin/env bash
#
# Faz a copia de seguranca sair da maquina, cifrada, para uma conta de nuvem.
#
# Ate aqui o dump ficava no disco externo da propria caixa. Isso resolve disco que
# morre e nao resolve box que some: perda, roubo ou incendio levam dado e copia juntos,
# e desde 13/11/2026 ha dado de cliente de verdade ali dentro.
#
# O que sobe e cifrado com AES256 antes de sair. Nao por capricho: o dump tem CPF, CNPJ,
# cadastro de cliente e trilha de auditoria, e passa a dormir no servidor de outra
# empresa. Regra 2 do CLAUDE.md — dado sensivel em primeiro lugar.
#
#     sudo ./configurar-backup-remoto.sh
#
# E seguro repetir: cada passo confere antes de fazer.

set -euo pipefail

DESTINO_PADRAO="drive:Decko/backups"
CONFIG_REMOTO=/etc/decko/backup-remoto.env
SENHA_ARQUIVO=/etc/decko/backup.pass
RCLONE_CONFIG_ARQUIVO=/etc/decko/rclone.conf

passo() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
erro() { printf '\033[1;31merro: %s\033[0m\n' "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || erro "rode com sudo."

# ------------------------------------------------------------------ 1. ferramentas

passo "ferramentas"
faltando=()
command -v rclone >/dev/null || faltando+=(rclone)
command -v gpg >/dev/null || faltando+=(gnupg)
if [ ${#faltando[@]} -gt 0 ]; then
    echo "instalando: ${faltando[*]}"
    apt-get update -qq
    apt-get install -y "${faltando[@]}"
fi
echo "rclone $(rclone version | head -1 | awk '{print $2}'), gpg $(gpg --version | head -1 | awk '{print $3}')"

# ------------------------------------------------------------------ 2. a senha do cofre

passo "senha que protege a copia"
if [ -f "$SENHA_ARQUIVO" ]; then
    echo "ja existe em $SENHA_ARQUIVO. Mantida."
    echo "Se voce perdeu a copia dela, as copias ja enviadas nao abrem mais."
else
    install -d -m 700 /etc/decko
    # 32 bytes de aleatoriedade do sistema, em base64. Nao e digitada por ninguem: e lida
    # do arquivo pelo gpg, e por isso pode ser longa de verdade.
    head -c 32 /dev/urandom | base64 > "$SENHA_ARQUIVO"
    chmod 600 "$SENHA_ARQUIVO"

    cat <<AVISO

  ######################################################################
  #                                                                    #
  #   GUARDE ESTA SENHA FORA DESTA MAQUINA, AGORA.                     #
  #                                                                    #
  #   Sem ela, nenhuma copia enviada para a nuvem volta a abrir —      #
  #   nem por voce, nem por ninguem. Ela nao esta no backup, de        #
  #   proposito: backup que carrega a propria chave nao protege de     #
  #   quem leva o backup.                                              #
  #                                                                    #
  #   Ponha no seu gerenciador de senhas antes de seguir.              #
  #                                                                    #
  ######################################################################

AVISO
    echo "  $(cat "$SENHA_ARQUIVO")"
    echo
    read -r -p "  Guardou? digite SIM para continuar: " resposta
    [ "$resposta" = "SIM" ] || erro "parado a seu pedido. A senha continua em $SENHA_ARQUIVO."
fi

# ------------------------------------------------------------------ 3. a conta de nuvem

passo "conta de nuvem"
export RCLONE_CONFIG="$RCLONE_CONFIG_ARQUIVO"

if rclone listremotes 2>/dev/null | grep -q '^drive:'; then
    echo "o destino 'drive' ja esta configurado."
else
    cat <<INSTRUCOES

  O rclone vai perguntar. As respostas:

    n                      (novo destino)
    drive                  (o nome — escreva exatamente assim)
    drive                  (o tipo: Google Drive)
    <enter>                (client_id vazio)
    <enter>                (client_secret vazio)
    1                      (acesso completo) ou 3 (so aos arquivos criados por ele)
    <enter>                (root_folder_id vazio)
    <enter>                (service_account_file vazio)
    n                      (nao editar configuracao avancada)
    n                      (NAO usar navegador automatico — esta caixa nao tem)

  Ai ele mostra um comando 'rclone authorize "drive" ...'. Rode ESSE comando num
  computador com navegador, entre na sua conta, e cole aqui o codigo que ele devolver.

INSTRUCOES
    rclone config
fi

rclone listremotes 2>/dev/null | grep -q '^drive:' || erro "o destino 'drive' nao ficou configurado."
chmod 600 "$RCLONE_CONFIG_ARQUIVO"

# ------------------------------------------------------------------ 4. onde guardar

passo "pasta no destino"
read -r -p "  caminho remoto [$DESTINO_PADRAO]: " destino
destino="${destino:-$DESTINO_PADRAO}"
rclone mkdir "$destino"
echo "ok: $destino"

cat > "$CONFIG_REMOTO" <<CONFIG
# Gerado por configurar-backup-remoto.sh. Lido pelo decko-backup.sh.
# Nenhum segredo aqui: a senha e o token moram em arquivos proprios, 600.
RCLONE_REMOTO=$destino
SENHA_ARQUIVO=$SENHA_ARQUIVO
RCLONE_CONFIG=$RCLONE_CONFIG_ARQUIVO
CONFIG
chmod 600 "$CONFIG_REMOTO"

# ------------------------------------------------------------------ 5. prova real

passo "copia de teste, do dump ate a nuvem e de volta"
/usr/local/sbin/decko-backup.sh

ultimo="$(rclone lsf "$destino" | sort | tail -1)"
[ -n "$ultimo" ] || erro "nada chegou em $destino."

# Baixa o que acabou de subir e abre. E a unica prova que vale: arquivo que sobe mas nao
# volta a ser um dump legivel e um backup que so falha no dia em que for preciso.
temporario="$(mktemp -d)"
trap 'rm -rf "$temporario"' EXIT
rclone copy "$destino/$ultimo" "$temporario/"
gpg --batch --quiet --decrypt --passphrase-file "$SENHA_ARQUIVO" --pinentry-mode loopback \
    "$temporario/$ultimo" 2>/dev/null | pg_restore --list >/dev/null \
    || erro "o arquivo baixado da nuvem nao abre como dump."

cat <<FIM

Pronto. A copia de 3h30 passa a subir cifrada para $destino, e fica 60 dias la.

Conferido de ponta a ponta: o arquivo $ultimo foi baixado da nuvem, decifrado e aberto
como dump valido nesta execucao.

Falta uma coisa so, e ela nao e tecnica: a senha em $SENHA_ARQUIVO precisa existir em
outro lugar que nao esta caixa. Se a caixa sumir com a unica copia da senha, as copias
na nuvem viram arquivo embaralhado.

FIM
