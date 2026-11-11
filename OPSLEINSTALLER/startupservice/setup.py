"""Command-line entry point for the first-start wizard."""

import sys

from setup_ui import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
