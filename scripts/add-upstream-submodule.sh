#!/usr/bin/env bash
set -euo pipefail
if [[ ! -d .git ]]; then
  echo 'Run this from the root of your own Git repository.' >&2
  exit 1
fi
if [[ -e third_party/docsgpt ]]; then
  echo 'third_party/docsgpt already exists, skipping.' >&2
  exit 1
fi
# This links the original repository with its attribution and history intact.
git submodule add https://github.com/arc53/DocsGPT.git third_party/docsgpt
printf '\nDocsGPT linked as an attributed upstream submodule. Run: git submodule update --init --recursive\n'
