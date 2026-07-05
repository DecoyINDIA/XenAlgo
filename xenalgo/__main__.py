from __future__ import annotations

import argparse
import json

from .config import load_config
from .logging_setup import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate XenAlgo Phase 0 configuration.")
    parser.add_argument("--profile", choices=["research", "live"], default="live")
    args = parser.parse_args()

    run_id = configure_logging()
    config = load_config(args.profile)
    print(json.dumps({"profile": config.profile, "checksum": config.checksum, "run_id": run_id}))


if __name__ == "__main__":
    main()
