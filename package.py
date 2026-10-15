# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Build the upload ZIP for the class app store.

Usage:
    python3 package.py --slug trade-structuring-agent --output ~/Downloads/trade-structuring-agent.zip
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--slug", required=True, help="Exact address claimed in My app.")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

manifest = json.loads((root / "workshop-app.json").read_bytes())
if manifest["slug"] != args.slug:
    parser.error(f'workshop-app.json uses "{manifest["slug"]}"; My app uses "{args.slug}". '
                 f'Set the manifest slug to "{args.slug}", then package again.')

# Published path in the ZIP -> source file in this project.
# The class store version has no outside packages, so its pyproject.toml and
# uv.lock come from deploy/ (the root ones are for the local Streamlit dashboard).
files = {
    "server.py": "server.py",
    "web/index.html": "web/index.html",
    "web/style.css": "web/style.css",
    "web/charts.js": "web/charts.js",
    "web/app.js": "web/app.js",
    "agent/__init__.py": "agent/__init__.py",
    "agent/broker.py": "agent/broker.py",
    "agent/market.py": "agent/market.py",
    "agent/pricing.py": "agent/pricing.py",
    "agent/recommender.py": "agent/recommender.py",
    "agent/strategies.py": "agent/strategies.py",
    "agent/view_parser.py": "agent/view_parser.py",
    "tests/test_pricing.py": "tests/test_pricing.py",
    "pyproject.toml": "deploy/pyproject.toml",
    "uv.lock": "deploy/uv.lock",
    "workshop-app.json": "workshop-app.json",
    "README.md": "README.md",
}
names = list(files)
# Local settings (.env, .venv) stay out of the ZIP.
data = {name: (root / source).read_bytes() for name, source in files.items()}

buffer = io.BytesIO()
with ZipFile(buffer, "w") as archive:
    for name, contents in sorted(data.items()):
        entry = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
        entry.create_system = 3
        entry.external_attr = 0o100644 << 16
        entry.compress_type = ZIP_DEFLATED
        archive.writestr(entry, contents)
payload = buffer.getvalue()

output = args.output.expanduser().absolute()
if output.suffix != ".zip":
    parser.error("--output must name a .zip file.")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(payload)
with ZipFile(output) as archive:
    assert set(archive.namelist()) == set(names)
print(json.dumps({"zip": str(output), "slug": args.slug, "sha256": hashlib.sha256(payload).hexdigest()}))
