#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${KASKAD_CONTAINER:-kaskad-web-vpn}"
IMAGE="${KASKAD_IMAGE:-kaskad-web-vpn:latest}"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  docker rm -f "$CONTAINER"
  echo "Контейнер ${CONTAINER} удалён."
else
  echo "Контейнер ${CONTAINER} не найден."
fi

if [[ "${REMOVE_IMAGE:-0}" == "1" ]]; then
  docker rmi "$IMAGE" 2>/dev/null && echo "Образ ${IMAGE} удалён." || echo "Образ ${IMAGE} не найден или занят."
fi
