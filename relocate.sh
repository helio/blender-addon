#!/usr/bin/env bash

set -Eeuo pipefail

export ADDON_DEBUG=true

${BLENDER_PATH} -b -y -P ./helio_blender_addon/paths.py "$1"
