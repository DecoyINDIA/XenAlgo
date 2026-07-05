from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse

from xenalgo.web.state import ConsoleStore


def create_app(
    store: ConsoleStore,
    *,
    control_token: str,
    postback_secret: str | None = None,
    config_root: str | Path | None = None,
) -> FastAPI:
    if not control_token:
        raise ValueError("control_token is required for Phase 2 operator actions")

    app = FastAPI(title="XenAlgo Console", version="2.0")

    def require_control_token(token: str | None) -> None:
        if not token or not hmac.compare_digest(token, control_token):
            raise HTTPException(status_code=401, detail="invalid console token")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "paper-console"}

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        return HTMLResponse(_render_dashboard(store.snapshot()))

    @app.get("/api/snapshot")
    def snapshot() -> dict[str, Any]:
        return store.snapshot()

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return store.config_summary("live", config_root)

    @app.get("/events")
    async def events(once: bool = False, interval_ms: int = 1000):
        if once:
            return PlainTextResponse(_sse("snapshot", store.snapshot()), media_type="text/event-stream")

        async def stream():
            while True:
                yield _sse("snapshot", store.snapshot())
                await asyncio.sleep(max(interval_ms, 250) / 1000)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/control/kill")
    def kill(
        x_xenalgo_console_token: str | None = Header(default=None),
        source: str = "dashboard",
        actor: str = "operator",
    ) -> dict[str, Any]:
        require_control_token(x_xenalgo_console_token)
        store.activate_kill(source=source, actor=actor)
        return {"ok": True, "kill_switch": "active", "snapshot": store.snapshot()["summary"]}

    @app.post("/control/rearm/{breaker}")
    def rearm(
        breaker: str,
        x_xenalgo_console_token: str | None = Header(default=None),
        actor: str = "operator",
        reason: str = "",
    ) -> dict[str, Any]:
        require_control_token(x_xenalgo_console_token)
        try:
            store.rearm(breaker, actor=actor, reason=reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "rearmed": breaker, "snapshot": store.snapshot()["summary"]}

    @app.post("/postback")
    async def postback(
        request: Request,
        x_xenalgo_postback_signature: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not postback_secret:
            raise HTTPException(status_code=503, detail="postback disabled")
        body = await request.body()
        expected = hmac.new(
            postback_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not x_xenalgo_postback_signature or not hmac.compare_digest(
            x_xenalgo_postback_signature,
            expected,
        ):
            raise HTTPException(status_code=401, detail="invalid postback signature")
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid json") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="postback payload must be an object")
        store.record_postback(payload)
        return {"ok": True, "enqueued": True}

    return app


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, sort_keys=True)}\n\n"


def _render_dashboard(snapshot: dict[str, Any]) -> str:
    summary = snapshot["summary"]
    orders = snapshot["orders"][:20]
    positions = snapshot["positions"]
    risk_state = snapshot["risk_state"]
    events = snapshot["recent_events"][:20]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>XenAlgo Console</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      background: #f6f8fb;
      color: #111827;
    }}
    body {{ margin: 0; }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; }}
    h1 {{ font-size: 28px; margin: 0; }}
    h2 {{ font-size: 16px; margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 20px 0; }}
    .panel {{ background: #ffffff; border: 1px solid #d8dee9; border-radius: 8px; padding: 14px; }}
    .value {{ font-size: 26px; font-weight: 700; }}
    .label {{ color: #526070; font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e5e7eb; padding: 8px; }}
    .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .danger {{ color: #b42318; font-weight: 700; }}
    @media (max-width: 820px) {{ .grid, .split {{ grid-template-columns: 1fr; }} main {{ padding: 14px; }} }}
    @media (prefers-color-scheme: dark) {{
      :root {{ background: #101418; color: #e5e7eb; }}
      .panel {{ background: #171d24; border-color: #2b3440; }}
      th, td {{ border-color: #2b3440; }}
      .label {{ color: #9aa6b2; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>XenAlgo Console</h1>
      <div class="label">Generated UTC: {snapshot["generated_utc"]}</div>
    </div>
    <div class="label">Paper-mode state surfaces</div>
  </header>
  <section class="grid">
    <div class="panel"><div class="value">{summary["open_orders"]}</div><div class="label">Open orders</div></div>
    <div class="panel"><div class="value">{summary["positions"]}</div><div class="label">Positions</div></div>
    <div class="panel"><div class="value">{summary["active_breakers"]}</div><div class="label">Active breakers</div></div>
    <div class="panel"><div class="value">{summary["events"]}</div><div class="label">Journal events</div></div>
  </section>
  <section class="split">
    <div class="panel"><h2>Risk State</h2>{_table(risk_state, ["key", "value", "updated_utc"], empty="No active breakers")}</div>
    <div class="panel"><h2>Positions</h2>{_table(positions, ["symbol", "qty", "avg_price", "sleeves"], empty="No positions")}</div>
  </section>
  <section class="panel" style="margin-top:12px"><h2>Orders</h2>{_table(orders, ["correlation_id", "broker_order_id", "state", "filled_qty", "avg_fill_price"], empty="No orders")}</section>
  <section class="panel" style="margin-top:12px"><h2>Recent Events</h2>{_table(events, ["event_id", "correlation_id", "symbol", "side", "state", "filled_qty", "reason"], empty="No journal events")}</section>
</main>
</body>
</html>"""


def _table(rows: list[dict[str, Any]], fields: list[str], *, empty: str) -> str:
    if not rows:
        return f'<div class="label">{empty}</div>'
    header = "".join(f"<th>{html.escape(field)}</th>" for field in fields)
    body = []
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            cls = ' class="danger"' if field == "state" and value == "REJECTED" else ""
            cells.append(f"<td{cls}>{html.escape(str(value))}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"
