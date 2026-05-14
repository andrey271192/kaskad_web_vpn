FROM docker:26-cli AS dockercli

FROM python:3.12-slim-bookworm

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# HTTP-зеркала иногда ломаются за прокси/кэшем → подпись InRelease «invalid».
# Чистим списки и переводим deb.debian.org / security на HTTPS перед update.
RUN set -eux; \
  apt-get clean; \
  rm -rf /var/lib/apt/lists/*; \
  if [ -f /etc/apt/sources.list ]; then \
    sed -i \
      -e 's|http://deb.debian.org|https://deb.debian.org|g' \
      -e 's|http://security.debian.org|https://security.debian.org|g' \
      /etc/apt/sources.list; \
  fi; \
  if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
    sed -i \
      -e 's|http://deb.debian.org|https://deb.debian.org|g' \
      -e 's|http://security.debian.org|https://security.debian.org|g' \
      /etc/apt/sources.list.d/debian.sources; \
  fi; \
  apt-get -o Acquire::Retries=5 update; \
  apt-get install -y --no-install-recommends ca-certificates iptables iproute2; \
  rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py kaskad_store.py system_info.py .
COPY templates ./templates
COPY static ./static

ENV PORT=8088
EXPOSE 8088

CMD ["sh", "-c", "exec gunicorn -w 2 -b 0.0.0.0:${PORT} app:app"]
