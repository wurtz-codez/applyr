"""Generate local-only configuration without overwriting an existing environment."""
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
(root / "storage").mkdir(exist_ok=True)
path = root / ".env"
if path.exists():
    print("Existing .env preserved.")
else:
    template = (root / ".env.example").read_text()
    content = template.replace("replace_with_a_generated_secret", secrets.token_urlsafe(48))
    with path.open("x") as handle:
        os.chmod(path, 0o600)
        handle.write(content)
    print("Created .env with a generated API token. Keep it private.")
