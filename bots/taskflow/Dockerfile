# --- stage 1: whisper.cpp (static CLI) + base model -------------------------
FROM debian:bookworm-slim AS whisper
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v1.7.6 https://github.com/ggerganov/whisper.cpp /whisper \
    && cd /whisper && cmake -B build -DBUILD_SHARED_LIBS=OFF && cmake --build build -j2 --config Release
RUN mkdir -p /models && curl -L --fail -o /models/ggml-base.bin \
        https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

# --- stage 2: the bot -------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=whisper /whisper/build/bin/whisper-cli /usr/local/bin/whisper-cli
COPY --from=whisper /models/ggml-base.bin /models/ggml-base.bin
ENV WHISPER_CLI_PATH=/usr/local/bin/whisper-cli WHISPER_MODEL_PATH=/models/ggml-base.bin
CMD ["python", "bot.py"]
