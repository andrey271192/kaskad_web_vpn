FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates
COPY static ./static

ENV PORT=8088
EXPOSE 8088

CMD ["sh", "-c", "exec gunicorn -w 2 -b 0.0.0.0:${PORT} app:app"]
