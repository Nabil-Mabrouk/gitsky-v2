#!/usr/bin/env bash
# Construit le livre GitSky en un seul PDF, à partir des chapitres Markdown.
#
# Pipeline : pandoc (Markdown -> HTML autonome stylé) puis Microsoft Edge en
# mode headless (HTML -> PDF). Edge/Chromium rend fidèlement emoji, flèches et
# caractères de dessin de boîte des diagrammes — là où LaTeX exigerait un
# bricolage de polices.
#
# Usage : bash docs/Template-book/pdf/build-pdf.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"          # .../docs/Template-book/pdf
BOOK="$(cd "$HERE/.." && pwd)"                  # .../docs/Template-book
OUT_HTML="$HERE/gitsky-book.html"
OUT_PDF="$BOOK/GitSky-livre.pdf"

EDGE="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
[ -x "$EDGE" ] || EDGE="/c/Program Files/Microsoft/Edge/Application/msedge.exe"

# Ordre : introduction, chap_01..chap_25, conclusion.
FILES=("$BOOK/introduction.md")
for f in "$BOOK"/chap_*.md; do FILES+=("$f"); done
FILES+=("$BOOK/conclusion.md")

echo "pandoc -> HTML (${#FILES[@]} fichiers)…"
pandoc "${FILES[@]}" \
  --from=markdown \
  --to=html5 \
  --standalone \
  --toc --toc-depth=2 \
  --number-sections \
  --highlight-style=kate \
  --embed-resources \
  --css="$HERE/book.css" \
  --metadata title="GitSky" \
  --metadata subtitle="Un template industriel pour la startup factory" \
  --metadata author="Nabil Mabrouk" \
  --metadata date="2026" \
  --metadata lang="fr" \
  -o "$OUT_HTML"

echo "Edge headless -> PDF…"
"$EDGE" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$(cygpath -w "$OUT_PDF" 2>/dev/null || echo "$OUT_PDF")" \
  "file:///$(cygpath -w "$OUT_HTML" 2>/dev/null | sed 's#\\#/#g' || echo "$OUT_HTML")" \
  2>/dev/null || true

if [ -f "$OUT_PDF" ]; then
  echo "OK -> $OUT_PDF"
else
  echo "ERREUR : le PDF n'a pas été généré." >&2
  exit 1
fi
