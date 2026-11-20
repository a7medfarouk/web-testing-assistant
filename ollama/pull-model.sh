#!/bin/sh
# One-shot: download the model only if the Ollama store doesn't already have it.
# The store is the host's ~/.ollama (bind-mounted), so a model pulled on the host
# before is found here and nothing is downloaded.
set -eu

if ollama show "$MODEL" >/dev/null 2>&1; then
  echo "[pull] $MODEL already present, skipping download."
else
  echo "[pull] $MODEL not found, pulling..."
  ollama pull "$MODEL"
fi
