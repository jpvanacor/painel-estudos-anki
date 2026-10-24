"""Builds dist/painel_estudos-<version>.ankiaddon, the file Anki installs.

The zip holds the add-on's files at its root, without a wrapping folder and without
__pycache__, as the Anki add-on docs require.
"""

import json
import re
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "painel_estudos"
VERSION = re.search(r'VERSION = "([^"]+)"', (SRC / "api.py").read_text(encoding="utf-8")).group(1)

manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
manifest["mod"] = int(time.time())
(SRC / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

out = ROOT / "dist" / f"painel_estudos-{VERSION}.ankiaddon"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(SRC.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        zf.write(path, path.relative_to(SRC).as_posix())
print(out)
