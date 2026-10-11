#!/bin/bash
set -euo pipefail
kit_dir=$(cd -- "$(dirname -- "$0")" && pwd)
if [[ $(uname -s) != Darwin ]]; then
  echo 'Build on an Apple Silicon Mac with Xcode 26 tools. No Apple SDK is bundled.' >&2
  exit 2
fi
xcrun --find clang >/dev/null
exec /usr/bin/python3 "$kit_dir/scripts/build.py" "$@"
