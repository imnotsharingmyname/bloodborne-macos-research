#!/bin/bash
set -euo pipefail
kit_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
exec /usr/bin/python3 "$kit_dir/scripts/package.py" "$@"
