from __future__ import annotations

import os
from pathlib import Path

from smart_display.app import create_app, serve_app
from smart_display.config import load_config, load_dotenv_values


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    env = _load_local_env(root)
    config = load_config(
        config_path=root / "config" / "local-demo.yaml",
        env=env,
        dotenv_path=None,
        root_dir=root,
    )
    app = create_app(config=config)
    serve_app(app)


def _load_local_env(root: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    for candidate in (root / ".env", root / ".env.local"):
        merged.update(load_dotenv_values(candidate))
    merged.update(os.environ)
    return merged


if __name__ == "__main__":  # pragma: no cover
    main()

