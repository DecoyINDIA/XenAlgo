from __future__ import annotations

import argparse
import ipaddress
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
    if not _is_allowed_bind_host(host):
        raise ValueError("console must bind only to loopback or a Tailscale 100.64.0.0/10 address")

    control_token = env.get("XENALGO_CONSOLE_TOKEN")
    if not control_token:
        raise ValueError("XENALGO_CONSOLE_TOKEN is required to run the console")

    return WebRuntime(
        host=host,
        port=int(web.get("bind_port", 8080)),
        journal_path=base / str(storage["journal_sqlite"]),
        control_token=control_token,
    )


def _is_allowed_bind_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError(f"console bind host must be an IP address, got {host!r}") from exc
    tailscale_cgnat = ipaddress.ip_network("100.64.0.0/10")
    return ip.is_loopback or ip in tailscale_cgnat


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
        config_root=root,
    )
    uvicorn.run(app, host=runtime.host, port=runtime.port)


if __name__ == "__main__":
    main()
