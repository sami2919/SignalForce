#!/usr/bin/env bash
# Recreate the venv with Python 3.12 and install the OpenAI Agents SDK.
# Run this from the repo root once you have network access:
#
#   ./setup_venv.sh
#
set -e

VENV_DIR="venv312"
PY="/opt/homebrew/bin/python3.12"

echo "Creating venv at $VENV_DIR with $PY ..."
"$PY" -m venv "$VENV_DIR"

echo "Installing openai-agents ..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install openai-agents

echo "Done!  Run the demo with:"
echo "  ./$VENV_DIR/bin/python openai_agents_sdk.py"
