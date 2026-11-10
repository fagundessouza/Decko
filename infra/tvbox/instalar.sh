#!/usr/bin/env bash
# Instala o Decko num servidor ARM pequeno — o caso que originou este script é um TV box
# Amlogic S912 com Armbian bookworm, 1,7 GB de RAM e 14 GB de memória interna.
#
# Rode como root, na máquina de destino:
#
#     ./instalar.sh --disco /dev/sda1
#
# O `--disco` é o armazenamento externo que vai receber o diretório de dados do
# PostgreSQL. **Ele é formatado**, e o script recusa um disco que tenha conteúdo.
# Sem `--disco`, o banco fica na memória interna — aceitável para experimentar, ruim
# para deixar ligado: escrita constante é o que mata memória flash de aparelho barato.
#
# É idempotente: rodar de novo não duplica nada e não apaga banco existente.
set -euo pipefail

DISCO=""
MONTAGEM=/srv/decko
REPO=https://github.com/fagundessouza/Decko.git
RAMO=main
PGVER=18
ORIGEM_WEB="${DECKO_ORIGEM_WEB:-https://decko-web.vercel.app}"

while [ $# -gt 0 ]; do
    case "$1" in
        --disco) DISCO="$2"; shift 2 ;;
        --ramo) RAMO="$2"; shift 2 ;;
        *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
    esac
done

[ "$(id -u)" -eq 0 ] || { echo "precisa ser root" >&2; exit 1; }

passo() { printf '\n=== %s\n' "$1"; }

# ---------------------------------------------------------------- 1. memória

passo "swap, porque 1,7 GB sem swap faz o sistema matar processo sozinho"
if systemctl list-unit-files 2>/dev/null | grep -q armbian-zram-config; then
    systemctl enable --now armbian-zram-config >/dev/null 2>&1 || true
fi
cat > /etc/sysctl.d/60-decko.conf <<'CONF'
# Swap como rede de segurança, não como caminho normal.
vm.swappiness=10
vm.vfs_cache_pressure=50
CONF
sysctl -q -p /etc/sysctl.d/60-decko.conf

# ---------------------------------------------------------------- 2. disco

if [ -n "$DISCO" ]; then
    passo "preparando $DISCO para o banco"
    tipo=$(blkid -s TYPE -o value "$DISCO" 2>/dev/null || echo "")
    if [ "$tipo" != "ext4" ]; then
        # Conferência antes de apagar. exFAT e NTFS não servem para diretório de dados
        # do PostgreSQL: não têm dono, permissão nem as garantias que o banco exige.
        tmp=$(mktemp -d)
        if mount -o ro "$DISCO" "$tmp" 2>/dev/null; then
            itens=$(find "$tmp" -mindepth 1 | wc -l)
            umount "$tmp"
            # "System Volume Information" do Windows conta 3 itens e não é conteúdo.
            [ "$itens" -gt 5 ] && { echo "o disco tem conteúdo ($itens itens) — recuso formatar" >&2; exit 1; }
        fi
        rmdir "$tmp"
        mkfs.ext4 -F -L DECKO -m 1 "$DISCO"
    fi

    mkdir -p "$MONTAGEM"
    uuid=$(blkid -s UUID -o value "$DISCO")
    sed -i "\|$MONTAGEM|d" /etc/fstab
    # noatime corta escrita desnecessária; nofail deixa a máquina subir sem o disco.
    echo "UUID=$uuid  $MONTAGEM  ext4  defaults,noatime,nofail  0  2" >> /etc/fstab
    systemctl daemon-reload
    mountpoint -q "$MONTAGEM" || mount "$MONTAGEM"

    if [ ! -f "$MONTAGEM/swapfile" ]; then
        fallocate -l 2G "$MONTAGEM/swapfile" || dd if=/dev/zero of="$MONTAGEM/swapfile" bs=1M count=2048 status=none
        chmod 600 "$MONTAGEM/swapfile"
        mkswap "$MONTAGEM/swapfile" >/dev/null
    fi
    swapon "$MONTAGEM/swapfile" 2>/dev/null || true
    grep -q "$MONTAGEM/swapfile" /etc/fstab || echo "$MONTAGEM/swapfile  none  swap  sw,nofail  0  0" >> /etc/fstab
else
    mkdir -p "$MONTAGEM"
fi

# ---------------------------------------------------------------- 3. PostgreSQL

passo "PostgreSQL $PGVER do repositório oficial"
# Do repositório da PGDG, e não do Debian: o Debian 12 só oferece o 15, e rodar o
# piloto numa major diferente do desenvolvimento e da esteira é diferença que só
# aparece em produção. A PGDG publica arm64 para bookworm.
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq ca-certificates gnupg curl >/dev/null
install -d /usr/share/postgresql-common/pgdg
curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc
. /etc/os-release
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
apt-get update -qq
apt-get install -y -qq "postgresql-$PGVER" "postgresql-client-$PGVER" >/dev/null

PGDATA="$MONTAGEM/pgdata"
if [ ! -d "$PGDATA/base" ]; then
    locale=$(locale -a 2>/dev/null | grep -iE '^pt_BR.utf-?8$' | head -1 || true)
    [ -z "$locale" ] && locale=C.UTF-8
    systemctl stop "postgresql@$PGVER-main" 2>/dev/null || true
    pg_dropcluster "$PGVER" main --stop 2>/dev/null || true
    mkdir -p "$PGDATA"
    chown postgres:postgres "$PGDATA"
    chmod 700 "$PGDATA"
    pg_createcluster --locale "$locale" -d "$PGDATA" "$PGVER" main >/dev/null
fi

mkdir -p "/etc/postgresql/$PGVER/main/conf.d"
grep -q "include_dir = 'conf.d'" "/etc/postgresql/$PGVER/main/postgresql.conf" || \
    echo "include_dir = 'conf.d'" >> "/etc/postgresql/$PGVER/main/postgresql.conf"
cat > "/etc/postgresql/$PGVER/main/conf.d/10-decko.conf" <<'CONF'
# Dimensionado para ~1,7 GB de RAM, dividindo a máquina com a API.
shared_buffers = 192MB
effective_cache_size = 512MB
work_mem = 4MB
maintenance_work_mem = 64MB
max_connections = 30

# Armazenamento é memória flash, com ciclo de escrita contado: checkpoint espaçado
# troca muitas escritas pequenas por poucas maiores.
wal_compression = on
checkpoint_timeout = 15min
max_wal_size = 1GB
min_wal_size = 128MB

# Flash não move cabeça de leitura: o padrão 4.0 faria o planejador evitar índice.
random_page_cost = 1.5
effective_io_concurrency = 200

# synchronous_commit fica LIGADO: o banco guarda dado fiscal de terceiro, e trocar
# durabilidade por velocidade aqui não se faz.
CONF
systemctl restart "postgresql@$PGVER-main"
systemctl enable postgresql.service >/dev/null 2>&1

# ---------------------------------------------------------------- 4. papéis e segredos

passo "papéis do banco e arquivo de ambiente"
# Dois papéis, como manda docs/adr/0002: decko_owner é dono do schema e só as migrações
# o usam; decko_app não é dono e não tem BYPASSRLS, e é isso que faz as políticas de
# Row Level Security valerem para a aplicação.
if ! su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='decko_app'\"" | grep -q 1; then
    s_owner=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)
    s_app=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)
    su postgres -c "psql -v ON_ERROR_STOP=1 -q" <<SQL
CREATE ROLE decko_owner LOGIN PASSWORD '$s_owner';
CREATE ROLE decko_app LOGIN PASSWORD '$s_app';
CREATE DATABASE decko OWNER decko_owner;
SQL
    su postgres -c "psql -d decko -v ON_ERROR_STOP=1 -q" <<'SQL'
GRANT USAGE ON SCHEMA public TO decko_app;
ALTER DEFAULT PRIVILEGES FOR ROLE decko_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO decko_app;
ALTER DEFAULT PRIVILEGES FOR ROLE decko_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO decko_app;
SQL

    # Segredo só em variável de ambiente, nunca em código — regra 3 do CLAUDE.md.
    mkdir -p /etc/decko
    umask 077
    cat > /etc/decko/decko.env <<ENV
DECKO_ENV=production
DECKO_DATABASE_URL=postgresql+asyncpg://decko_app:$s_app@127.0.0.1:5432/decko
DECKO_MIGRATION_DATABASE_URL=postgresql+psycopg://decko_owner:$s_owner@127.0.0.1:5432/decko
DECKO_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n')
DECKO_CORS_ORIGINS=$ORIGEM_WEB
DECKO_BREACH_CHECK_ENABLED=true
DECKO_DB_POOL_SIZE=5
DECKO_DB_MAX_OVERFLOW=5
ENV
    chmod 600 /etc/decko/decko.env
fi

# ---------------------------------------------------------------- 5. aplicação

passo "aplicação"
id decko >/dev/null 2>&1 || useradd --system --home-dir "$MONTAGEM" --shell /usr/sbin/nologin decko
mkdir -p "$MONTAGEM/app" "$MONTAGEM/.cache" "$MONTAGEM/.local/share/uv"
chown -R decko:decko "$MONTAGEM/app" "$MONTAGEM/.cache" "$MONTAGEM/.local"

command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh >/dev/null

if [ -d "$MONTAGEM/app/.git" ]; then
    su -s /bin/bash decko -c "cd $MONTAGEM/app && git fetch -q origin && git checkout -q $RAMO && git reset -q --hard origin/$RAMO"
else
    su -s /bin/bash decko -c "git clone -q --branch $RAMO $REPO $MONTAGEM/app"
fi

# O projeto exige Python 3.13 e o Debian 12 traz 3.11 — o uv baixa a versão certa.
su -s /bin/bash decko -c "cd $MONTAGEM/app && HOME=$MONTAGEM uv sync --frozen --no-dev"

passo "migrações"
set -a; . /etc/decko/decko.env; set +a
su -s /bin/bash decko -c "cd $MONTAGEM/app && HOME=$MONTAGEM \
    DECKO_MIGRATION_DATABASE_URL='$DECKO_MIGRATION_DATABASE_URL' \
    DECKO_DATABASE_URL='$DECKO_DATABASE_URL' \
    DECKO_SECRET_KEY='$DECKO_SECRET_KEY' \
    uv run --frozen --no-dev alembic -c apps/api/alembic.ini upgrade heads"

# ---------------------------------------------------------------- 6. serviços

passo "serviços"
install -m 644 "$(dirname "$0")/decko-api.service" /etc/systemd/system/
install -m 644 "$(dirname "$0")/decko-tunel.service" /etc/systemd/system/
install -m 750 "$(dirname "$0")/decko-backup.sh" /usr/local/sbin/
install -m 750 "$(dirname "$0")/decko-testar-restauracao.sh" /usr/local/sbin/
install -m 644 "$(dirname "$0")/decko-backup.service" /etc/systemd/system/
install -m 644 "$(dirname "$0")/decko-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now decko-api.service decko-tunel.service decko-backup.timer >/dev/null

passo "pronto"
systemctl is-active postgresql@$PGVER-main decko-api decko-tunel | paste -sd' ' -
echo "a URL pública sai no journal do túnel:"
echo "    journalctl -u decko-tunel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1"
