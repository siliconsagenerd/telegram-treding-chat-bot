from __future__ import annotations

import sys

from derivatives_scanner.main import cli_main


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.extend(["--mode", "model_sync"])
    cli_main()
