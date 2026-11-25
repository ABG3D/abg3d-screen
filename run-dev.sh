#!/usr/bin/env bash
# Run from the source tree in a window, for testing on a desktop VM.
cd "$(dirname "$0")" && exec python3 -m abg3d_screen --windowed "$@"
