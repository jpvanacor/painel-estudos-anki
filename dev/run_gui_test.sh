#!/usr/bin/env bash
# Runs real Anki on a virtual display with the add-on and the demo driver, then checks the
# review log. Usage: dev/run_gui_test.sh <work folder>
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${1:?work folder}"
BASE="$WORK/base"
SHOTS="$WORK/shots"
rm -rf "$BASE" "$SHOTS"
mkdir -p "$BASE/addons21" "$SHOTS"
python3 "$REPO/dev/make_test_profile.py" "$BASE"
cp -r "$REPO/painel_estudos" "$BASE/addons21/painel_estudos"
cp -r "$REPO/dev/demo_addon" "$BASE/addons21/painel_demo"
find "$BASE/addons21" -name __pycache__ -prune -exec rm -rf {} +
PAINEL_SHOTS="$SHOTS" PAINEL_FIXTURE="$REPO/dev/fixtures/roleta-backup.json" QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu" QTWEBENGINE_DISABLE_SANDBOX=1 \
  timeout 300 xvfb-run -a -s "-screen 0 1280x800x24" python3 -c "import aqt; aqt.run()" -b "$BASE" -p Teste \
  > "$WORK/run.log" 2>&1 || echo "anki exit code: $?"
python3 "$REPO/dev/check_review_log.py" "$BASE/Teste/collection.anki2"
