from __future__ import annotations

import shutil
import tempfile
import zipapp
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "acc.pyz"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="acc-zipapp-") as temporary:
        stage = Path(temporary)
        shutil.copytree(ROOT / "acc", stage / "acc")
        (stage / "__main__.py").write_text(
            "from acc.server import main\n\nmain()\n", encoding="utf-8"
        )
        zipapp.create_archive(
            stage,
            target=OUTPUT,
            interpreter="/usr/bin/env python3",
            compressed=True,
        )
    print(f"Built {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
