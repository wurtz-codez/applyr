"""Run from apps/api: uv run python ../../scripts/export_openapi.py"""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "apps/api"))
from app.main import app  # noqa: E402

path = root / "packages/contracts/openapi.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"Exported {path.relative_to(root)}")
