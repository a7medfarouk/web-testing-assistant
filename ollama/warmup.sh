#!/bin/sh
# Sidecar: keep $MODEL loaded in memory so the first real prompt has no load delay.
# It generates one token (loads weights and runs a first forward pass), then keeps
# checking /api/ps and warms again if the model was ever unloaded (e.g. Ollama restart).
set -u

while true; do
  if curl -fsS "$OLLAMA_URL/api/ps" 2>/dev/null | grep -qF "\"name\":\"$MODEL\""; then
    sleep 30
    continue
  fi

  echo "[warmup] loading $MODEL..."
  if curl -fsS "$OLLAMA_URL/api/generate" -o /dev/null \
      -d "{\"model\":\"$MODEL\",\"prompt\":\"Hello\",\"stream\":false,\"keep_alive\":-1,\"options\":{\"num_predict\":1}}"; then
    echo "[warmup] $MODEL is loaded and ready."
  else
    echo "[warmup] failed, retrying in 10s"
    sleep 10
  fi
done
