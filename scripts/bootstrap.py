"""Create private configuration without replacing existing credentials."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
storage = root / "storage"
storage.mkdir(mode=0o700, exist_ok=True)
os.chmod(storage, 0o700)
path = root / ".env"
if path.exists():
    print("Existing .env preserved. Add TAVILY_API_KEY there for web search.")
else:
    value = (
        (root / ".env.example")
        .read_text()
        .replace("replace_with_generated_token", secrets.token_urlsafe(48))
    )
    with path.open("x") as handle:
        os.chmod(path, 0o600)
        handle.write(value)
    print("Created private .env. Add TAVILY_API_KEY for web search.")
