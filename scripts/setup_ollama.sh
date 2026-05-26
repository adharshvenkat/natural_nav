#!/bin/bash
# Pulls the LLM model into the Ollama service. Run once after `docker compose up -d ollama`.
# Usage: ./scripts/setup_ollama.sh [model]
set -e

MODEL="${1:-qwen2.5:3b}"

echo "Waiting for Ollama service to be ready..."
until curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; do
  sleep 2
done

echo "Pulling model: $MODEL"
docker compose exec ollama ollama pull "$MODEL"

echo "Done. Available models:"
docker compose exec ollama ollama list
