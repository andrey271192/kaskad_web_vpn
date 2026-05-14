FROM docker:27-cli AS dockercli

FROM python:3.12-slim-bookworm

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends iptables iproute2 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py kaskad_store.py system_info.py .
COPY templates ./templates
COPY static ./static

ENV PORT=8088
EXPOSE 8088

CMD ["sh", "-c", "exec gunicorn -w 2 -b 0.0.0.0:${PORT} app:app"]
