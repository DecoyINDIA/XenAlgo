from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import uvicorn

from xenalgo.config import RuntimeConfig, load_config
from xenalgo.web.app import create_app
from xenalgo.web.state import ConsoleStore


@dataclass(frozen=True)
class WebRuntime:
    host: str
    port: int
    journal_path: Path
    control_token: str
    postback_secret: str | None


def runtime_from_config(
    config: RuntimeConfig,
    *,
    env: Mapping[str, str] | None = None,
    root: str | Path | None = None,
) -> WebRuntime:
    env = env or os.environ
    base = Path(root) if root is not None else config.path.parents[1]
    web = config.section("web")
    storage = config.section("storage")

    host_env = str(web.get("bind_host_env", "TAILSCALE_BIND_HOST"))
    host = env.get(host_env, "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        raise ValueError("console must bind to loopback or a Tailscale interface, not a public wildcard")

    control_token = env.get("XENALGO_CONSOLE_TOKEN")
    if not control_token:
        raise ValueError("XENALGO_CONSOLE_TOKEN is required to run the console")

    postback_secret = None
    if web.get("public_postback_enabled") is True:
        secret_env = str(web.get("postback_hmac_secret_env", "POSTBACK_HMAC_SECRET"))
        postback_secret = env.get(secret_env)
        if not postback_secret:
            raise ValueError(f"{secret_env} is required when public postback is enabled")

    return WebRuntime(
        host=host,
        port=int(web.get("bind_port", 8080)),
        journal_path=base / str(storage["journal_sqlite"]),
        control_token=control_token,
        postback_secret=postback_secret,
    )


def build_app_from_config(
    profile: str = "live",
    *,
    root: str | Path | None = None,
    env: Mapping[str, str] | None = None,
):
    config = load_config(profile, root)
    runtime = runtime_from_config(config, env=env, root=root)
    return create_app(
        ConsoleStore(runtime.journal_path),
        control_token=runtime.control_token,
        postback_secret=runtime.postback_secret,
        config_root=root,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the XenAlgo Phase 2 operator console.")
    parser.add_argument("--profile", choices=["live"], default="live")
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    root = Path(args.root) if args.root else None
    config = load_config(args.profile, root)
    runtime = runtime_from_config(config, root=root)
    app = create_app(
        ConsoleStore(runtime.journal_path),
        control_token=runtime.control_token,
        postback_secret=runtime.postback_secret,
        config_root=root,
    )
    uvicorn.run(app, host=runtime.host, port=runtime.port)


if __name__ == "__main__":
    main()
