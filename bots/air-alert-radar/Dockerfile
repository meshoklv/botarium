FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 STATE_DB=/data/state.db
WORKDIR /app
COPY bot.py .
# config.json is mounted at runtime (see docker-compose.yml); BOT_TOKEN / ADMIN_ID env vars also work
CMD ["python", "/app/bot.py"]
