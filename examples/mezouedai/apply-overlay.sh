#!/usr/bin/env bash
# Applique l'overlay MezouedAI (code bespoke non exprimable en config générateur :
# routeur métier, pages front, agents…) par-dessus un projet généré.
#
# Usage : ./apply-overlay.sh <chemin-du-projet-généré>
set -euo pipefail
DST="${1:?Usage: apply-overlay.sh <chemin-projet-généré>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cp -r "$HERE/overlay/." "$DST/"
echo "Overlay appliqué sur $DST"
