#!/usr/bin/env bash
# Render .pptx/.xlsx to PDF with LibreOffice using a throwaway profile that contains the shipped fonts.
# Usage: tools/render_office.sh <out_dir> <file>...   (requires: soffice)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$1"; shift
PROFILE="$(mktemp -d)"
mkdir -p "$PROFILE/user/fonts" "$OUT"
cp "$ROOT"/assets/fonts/InterTabular-*.ttf "$PROFILE/user/fonts/"
soffice -env:UserInstallation="file://$PROFILE" --headless --convert-to pdf --outdir "$OUT" "$@" >/dev/null 2>&1
rm -rf "$PROFILE"
