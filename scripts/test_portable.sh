#!/bin/bash
set -euo pipefail
kit_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
python3 -m unittest discover -s "$kit_dir/tests" -p 'test_*.py' -v
test_binary=$(mktemp /tmp/bb-pipeline-test.XXXXXX)
trap 'rm -f "$test_binary"' EXIT
cxx_bin=${CXX:-c++}
"$cxx_bin" -std=c++17 -Wall -Wextra -Werror -pthread "$kit_dir/tests/test_pipeline_store.cpp" -o "$test_binary"
"$test_binary"
echo 'Pipeline cache contracts passed.'
