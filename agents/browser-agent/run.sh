#!/bin/bash
# Wrapper to run the browser-agent CLI with the venv python.
cd "$(dirname "$0")"
exec ./.venv/bin/python cli.py "$@"
