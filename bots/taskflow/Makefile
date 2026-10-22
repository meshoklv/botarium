# Local speech recognition without Docker: builds whisper.cpp and downloads a model.
# (The Docker image does the same at build time.)
WHISPER_REPO = https://github.com/ggerganov/whisper.cpp.git
WHISPER_TAG  = v1.7.6
MODEL_NAME   = ggml-base.bin
MODEL_URL    = https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$(MODEL_NAME)

.PHONY: setup-speech install-whisper download-model clean help

help:
	@echo "make setup-speech   - build whisper.cpp + download the base model (needs git, cmake, a C++ compiler, ffmpeg)"
	@echo "make clean          - remove whisper.cpp and models"

setup-speech: install-whisper download-model
	@echo "Speech recognition ready: ./whisper.cpp/build/bin/whisper-cli + ./models/$(MODEL_NAME)"

install-whisper:
	@test -d whisper.cpp || git clone --depth 1 --branch $(WHISPER_TAG) $(WHISPER_REPO) whisper.cpp
	cd whisper.cpp && cmake -B build -DBUILD_SHARED_LIBS=OFF && cmake --build build -j2 --config Release

download-model:
	@mkdir -p models
	@test -f models/$(MODEL_NAME) || curl -L --fail -o models/$(MODEL_NAME) $(MODEL_URL)

clean:
	rm -rf whisper.cpp models
