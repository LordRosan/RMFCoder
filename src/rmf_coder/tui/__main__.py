from __future__ import annotations

import argparse

from rmf_coder.core.config import get_config
from rmf_coder.tui.app import RMFTuiApp


def main() -> None:
    parser = argparse.ArgumentParser(prog="rmf-tui", description="RMFCoder TUI")
    parser.add_argument(
        "--replay",
        metavar="RUN_ID",
        help="Replay events from a past run on connect",
    )
    args = parser.parse_args()

    config = get_config()
    app = RMFTuiApp(config.host, config.port, replay_run_id=args.replay)
    app.run()


if __name__ == "__main__":
    main()
