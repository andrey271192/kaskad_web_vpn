#!/usr/bin/env bash
# Однострочная установка: GitHub → сборка образа → контейнер с NAT на хосте (privileged + host network).
set -euo pipefail

REPO="${KASKAD_REPO:-andrey271192/kaskad_web_vpn}"
REF="${KASKAD_REF:-main}"
IMAGE="${KASKAD_IMAGE:-kaskad-web-vpn:latest}"
CONTAINER="${KASKAD_CONTAINER:-kaskad-web-vpn}"
INSTALL_ROOT="${KASKAD_INSTALL_ROOT:-/opt}"
HOST_PORT="${HOST_PORT:-8088}"
BASIC_AUTH_USER="${BASIC_AUTH_USER:-user1}"
BASIC_AUTH_REALM="${BASIC_AUTH_REALM:-kaskad}"
PASSWORD_FILE="${PASSWORD_FILE:-/root/kaskad_web.initial-password}"
PANEL_URL="${PANEL_URL:-}"
KASKAD_DATA_DIR="${KASKAD_DATA_DIR:-/var/lib/kaskad}"
KASKAD_HOST_NETWORK="${KASKAD_HOST_NETWORK:-1}"
MOUNT_DOCKER_SOCK="${MOUNT_DOCKER_SOCK:-1}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Нужна команда: $1" >&2
    exit 1
  }
}

need_cmd docker

if ! docker info >/dev/null 2>&1; then
  echo "Docker недоступен (запустите сервис или добавьте пользователя в группу docker)." >&2
  exit 1
fi

mkdir -p "$KASKAD_DATA_DIR"

SRC="${INSTALL_ROOT}/kaskad_web_vpn_src"
mkdir -p "$(dirname "$SRC")"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz"
echo "Скачивание ${ARCHIVE_URL} …"
curl -fsSL "$ARCHIVE_URL" -o "${TMP}/src.tar.gz"
tar -xzf "${TMP}/src.tar.gz" -C "$TMP"
EXTRACTED="$(find "$TMP" -maxdepth 1 -type d -name "*-${REF}" | head -n1)"
if [[ -z "$EXTRACTED" ]]; then
  EXTRACTED="$(find "$TMP" -maxdepth 1 -type d ! -path "$TMP" | head -n1)"
fi
rm -rf "$SRC"
mkdir -p "$SRC"
shopt -s dotglob
mv "$EXTRACTED"/* "$SRC"/

echo "Сборка образа ${IMAGE} …"
docker build -t "$IMAGE" "$SRC"

FORCE_RANDOM_PASSWORD="${FORCE_RANDOM_PASSWORD:-0}"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Удаление старого контейнера ${CONTAINER} …"
  docker rm -f "$CONTAINER" >/dev/null
fi

AUTH_ENV_ARGS=()

if [[ -n "${ADMIN_PASSWORD:-}" ]]; then
  AUTH_ENV_ARGS+=( -e "BASIC_AUTH_PASSWORD=${ADMIN_PASSWORD}" )
elif [[ -f "$PASSWORD_FILE" ]] && grep -qs . "$PASSWORD_FILE"; then
  AUTH_ENV_ARGS+=( -e "BASIC_AUTH_PASSWORD=$(tr -d '\r\n' <"$PASSWORD_FILE")" )
elif [[ "$FORCE_RANDOM_PASSWORD" == "1" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    GEN_PW="$(openssl rand -hex 16)"
  else
    GEN_PW="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)"
  fi
  umask 077
  printf '%s\n' "$GEN_PW" >"$PASSWORD_FILE"
  AUTH_ENV_ARGS+=( -e "BASIC_AUTH_PASSWORD=${GEN_PW}" )
  echo "Сгенерирован пароль (FORCE_RANDOM_PASSWORD=1), файл ${PASSWORD_FILE}"
else
  echo "Пароль веб-панели: откройте http://<хост>:${HOST_PORT}/setup при первом запуске (том ${KASKAD_DATA_DIR})."
fi

RUN_ARGS=(
  -d
  --name "$CONTAINER"
  --restart unless-stopped
  --privileged
  -v "${KASKAD_DATA_DIR}:/var/lib/kaskad"
  -e "KASKAD_RULES_PATH=/var/lib/kaskad/rules.json"
  -e "DOCKER_WEB_CONTAINER=${CONTAINER}"
  -e "DOCKER_WEB_DISPLAY_UNIT=kaskad-web.service"
  -e "BASIC_AUTH_USER=${BASIC_AUTH_USER}"
  -e "BASIC_AUTH_REALM=${BASIC_AUTH_REALM}"
  -e "KASKAD_IPTABLES_MODE=${KASKAD_IPTABLES_MODE:-compat}"
)

RUN_ARGS+=("${AUTH_ENV_ARGS[@]}")

if [[ "${MOUNT_DOCKER_SOCK:-1}" == "1" ]] && [[ -S /var/run/docker.sock ]]; then
  RUN_ARGS+=( -v /var/run/docker.sock:/var/run/docker.sock )
fi

if [[ -n "$PANEL_URL" ]]; then
  RUN_ARGS+=( -e "PANEL_URL=${PANEL_URL}" )
fi

if [[ "$KASKAD_HOST_NETWORK" == "1" ]]; then
  RUN_ARGS+=( --network host )
  RUN_ARGS+=( -e "PORT=${HOST_PORT}" )
else
  RUN_ARGS+=( -p "${HOST_PORT}:8088" )
  RUN_ARGS+=( -e "PORT=8088" )
fi

docker run "${RUN_ARGS[@]}" "$IMAGE"

echo "Готово."
echo "  URL:    http://$(hostname -f 2>/dev/null || hostname):${HOST_PORT}/"
echo "  Логин: ${BASIC_AUTH_USER}"
if [[ "${#AUTH_ENV_ARGS[@]}" -gt 0 ]]; then
  echo "  Пароль: из ADMIN_PASSWORD / ${PASSWORD_FILE} / автогенерация (см. выше)."
else
  echo "  Пароль: создайте на странице /setup при первом открытии."
fi
echo "  NAT: режим ${KASKAD_IPTABLES_MODE:-compat}, данные: ${KASKAD_DATA_DIR}"
echo "  Рекомендуется: sysctl net.ipv4.ip_forward=1."
