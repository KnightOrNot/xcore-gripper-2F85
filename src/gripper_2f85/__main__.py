"""Allow ``python -m gripper_2f85`` to run the command line interface."""

from __future__ import annotations

from gripper_2f85.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
