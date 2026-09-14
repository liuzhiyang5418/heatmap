"""支持 ``python -m githotmap`` 直接运行 CLI。"""

from __future__ import annotations

from githotmap.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
