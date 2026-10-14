# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Build the upload ZIP for the class app store.

Usage:
    uv run --locked python package.py --slug trade-structuring-agent --output ~/Downloads/trade-structuring-agent.zip
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

names = [
    "app.py",
    "run.py",
    "agent/__init__.py",
    "agent/broker.py",
    "agent/market.py",
    "agent/pricing.py",
    "agent/recommender.py",
    "agent/strategies.py",
    "agent/view_parser.py",
    "tests/test_pricing.py",
    "pyproject.toml",
    "uv.lock",
    "workshop-app.json",
    "README.md",
    "package.py",
]
# Local settings (.env, .venv, .streamlit) stay out of the ZIP.
data = {name: (root / name).read_bytes() for name in names}

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
