# Fyers v3 Contract and Runtime Decision Record

**Frozen:** 2026-07-12  
**Scope:** B0 contract freeze for paper commissioning.  
**Authority:** Current FYERS support/API-v3 material; verify again before live activation.

## Authoritative decisions

1. Fyers is the only active broker contract. Historical references to Dhan describe
   research-data provenance only and are not runtime requirements.
2. The production paper daemon receives live Fyers data but is hard-wired to
   `PaperBroker`. Credentials cannot make that composition place a real order.
3. From 2026-04-01, an order-capable app requires a whitelisted static IP and a daily
   2FA-authenticated session. Continuous refresh-token operation is not an accepted
   commissioning assumption. Auth failure or timeout halts the session.
4. The internal governor remains at 2 orders/second, below the external 10 orders/second
   ceiling. Broker limits are never treated as the system safety control.
5. Order identity is the XenAlgo deterministic correlation id carried in the Fyers `tag`.
   Before submission, the gateway checks the current order book for that tag. A POST is
   never blindly retried.
6. Fill truth is cumulative filled quantity for a broker order. Fyers Order WebSocket and
   REST order-book polling normalize into the same idempotent listener. Terminal states are
   `TRADED`, `REJECTED`, `CANCELLED`, and `EXPIRED`; partial fills are `PART_TRADED`.
7. NSE cash symbols use the canonical `NSE:<SYMBOL>-EQ` form and must resolve uniquely from
   a fresh instrument master before sizing or order construction.
8. There is no public postback endpoint and no broker-side kill-switch API acceptance
   criterion. XenAlgo preserves the kill SLA through the local kill switch, session-token
   revocation, process supervision, account capital cap, and reconciliation halt.
9. `fyers-apiv3` remains behind injected adapters. Importing or installing the SDK is not
   required for mock-only CI or the production paper composition.

## Frozen interfaces

The broker-neutral contracts are in `xenalgo/broker/contracts.py`:

- `AuthProvider`
- `MarketDataProvider`
- `OrderGateway`
- `FillStream`
- `OrderbookPoller`

All order submission remains owned by `ExecutionEngine`, which applies `RiskEngine.check()`
and `OrderGovernor` before calling an injected `OrderGateway`.

## Operator-owned decisions

These remain explicit blockers for live activation and do not default silently:

- dedicated Fyers account and initial capital amount;
- sleeve weights;
- final breaker thresholds;
- paid live host choice and registered static IPs;
- the approved daily 2FA operating mechanism for the live host.

## Official sources checked

- FYERS, “What are the new SEBI rules for retail algo trading from April 01, 2026?”
  (static IP, daily 2FA, 10 OPS, MPP):
  https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026
- FYERS, “Activate the new FYERS API app before April 1, 2026” (new app, permissions,
  static-IP activation, data-only behavior for old apps):
  https://support.fyers.in/portal/en/kb/articles/how-do-i-activate-the-new-app-for-api-trading-after-april-1-2026
- FYERS API v3 support index (Order WebSocket and official sample-code references):
  https://support.fyers.in/portal/en/kb/fyers-api-integrations/fyers-api/api-v3/general
