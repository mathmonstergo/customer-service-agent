"""支持 `python -m cyclops`；关键约束是直接使用真实 Cyclops CLI。"""

from __future__ import annotations

from cyclops.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
