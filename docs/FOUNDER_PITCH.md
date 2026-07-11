# XenAlgo Founder Pitch

## The one-line explanation

XenAlgo is a safety-first trading bot for Indian shares. It is designed to run three tested
investment strategies automatically, while an independent risk system checks every proposed
trade before anything can reach the broker.

> The strategies decide what they want to buy or sell. XenAlgo decides whether that action
> is safe, records what happened, watches the broker for the real result, and gives the owner
> a private control room with an emergency stop button.

## The founder story

Most people hear “trading bot” and imagine software that finds a stock and instantly places
an order. That is only the visible part. The difficult and dangerous part is everything
around the decision:

- What if the market data is old or corrupted?
- What if the bot restarts after sending an order and sends it again?
- What if the broker accepts an order but does not fill it?
- What if only part of an order is filled?
- What if the bot’s records disagree with the broker?
- What if losses become larger than expected?
- What if the owner needs to stop the system immediately?

XenAlgo is being built around those questions. Its purpose is not merely to automate stock
selection. Its purpose is to make automated trading controlled, explainable, restart-safe
and auditable.

## What the bot is intended to trade

XenAlgo is designed for NSE-listed Indian equities through the Dhan broker. It is a swing
trading system, not a high-frequency or intraday scalping system.

Swing trading means positions may be held for days or weeks. The system uses completed daily
market data and operates around a controlled execution window near the market close. It does
not need microsecond speed. Correctness matters more than saving a few milliseconds.

The project contains three pre-validated strategies:

1. `std30`
2. `alpha_027`
3. `alpha_062`

We treat them like three portfolio managers working inside one company. Each receives its
own portion of capital—called a **capital sleeve**—and its performance is tracked separately.
This prevents one strategy from silently consuming the money intended for another.

The strategy logic is deliberately protected from casual changes. Changing a validated
strategy without re-testing it properly would make its past research less meaningful.

## How the complete daily flow is intended to work

```text
Market data arrives
        |
        v
Data quality and freshness checks
        |
        v
Three strategies calculate desired portfolios
        |
        v
Capital sleeves size their own positions
        |
        v
Opposing requests are netted into fewer proposed orders
        |
        v
Independent RiskEngine checks every proposed order
        |
        v
Execution system records intent before contacting the broker
        |
        v
PaperBroker during testing / Dhan gateway only after go-live approval
        |
        v
Confirmed fill events update positions
        |
        v
Reconciliation compares our records with broker truth
        |
        v
Dashboard, alerts, journal and daily review are updated
```

In founder language: the strategy is the idea generator, the RiskEngine is the compliance
officer, the execution engine is the operations team, the broker is the external bank, and
reconciliation is the accountant checking that both sets of books agree.

## What happens before a trade

### 1. The system checks whether today is safe to operate

The scheduler understands Indian Standard Time, NSE trading days, holidays and the permitted
execution window. It is designed to refuse trading outside that window.

The startup gate must also confirm that configuration is valid, the clock is synchronized,
market data is current, required authentication is valid, and local records reconcile with
the broker. If a required check fails, the intended behaviour is to stop—not guess.

### 2. Market data is checked before strategies see it

The system checks whether the newest candle belongs to the expected trading date and whether
prices contain impossible, missing or corrupted values. Old data pretending to be new data
is one of the most dangerous failures in an automated trading system.

The rule is simple: **stale or suspicious data means no new trades**.

### 3. Each strategy creates a desired portfolio

The three strategies independently calculate which shares they would like to own. Each works
inside its own capital allocation and position limits.

If one strategy wants to buy a share while another wants to sell it, XenAlgo can net those
requests. Instead of paying fees and creating unnecessary broker traffic twice, the
execution layer can send only the remaining difference.

### 4. The RiskEngine can veto the strategy

No strategy has direct access to the broker. Every proposed order must pass the independent
RiskEngine.

Checks include:

- maximum rupee value per order;
- maximum exposure to one company;
- sufficient cash, including a fee buffer;
- liquidity limits based on market volume;
- a price collar to reject unreasonable prices;
- restricted or blacklisted securities;
- duplicate-order detection;
- maximum number of positions;
- daily-loss, drawdown and operational circuit breakers;
- the global emergency kill switch.

The strategy can request a trade. It cannot force the RiskEngine to approve it.

### 5. The order is recorded before it is sent

Before any future live broker request, XenAlgo writes an **intent event** into an append-only
SQLite journal. Think of this as a permanent flight recorder.

Every order receives a deterministic `correlationId`, created from facts such as date,
strategy sleeve, symbol, direction and rebalance sequence. If the server crashes and
restarts, the system can identify the same order instead of blindly creating a second one.

### 6. A submitted order is not treated as a completed trade

An order can be submitted, pending, partially filled, fully filled, rejected, cancelled or
expired. XenAlgo tracks those as different states.

> A position changes only after the broker confirms an actual fill.

“Order accepted” does not mean “shares purchased.” This rule prevents the bot from building
an imaginary portfolio based on orders that never completed.

### 7. Reconciliation checks the truth

After execution, XenAlgo compares its journal-derived holdings with the broker’s holdings and
positions. The broker is treated as the final source of truth.

If the two sides disagree, the system is designed to halt new trading and alert the owner.
It should never carry a mystery mismatch overnight and hope it fixes itself.

## The safety system in plain English

XenAlgo uses several independent layers rather than relying on one perfect component.

### Pre-trade protection

Every proposed trade is checked for size, price, cash, liquidity, duplicates, restrictions
and portfolio concentration.

### Portfolio circuit breakers

The system can halt new trading when it detects excessive daily loss, excessive drawdown,
stale data, repeated order failures or a reconciliation mismatch.

### Rate limiting and compliance margin

The internal governor is capped at two orders per second. This stays far below the planned
SEBI threshold of ten orders per second for the relevant retail-algo boundary and prevents
an accidental order storm.

### Emergency controls

The design includes three stop paths:

- private dashboard kill switch;
- Telegram operator command;
- Dhan’s broker-side control path for the future live system.

The private dashboard kill switch has already been tested from the operator’s Windows laptop
to the Oracle server over Tailscale. It activated in 333 milliseconds, appeared in persisted
risk state, and was then rearmed through an audited endpoint.

### Blast-radius control

The intended live deployment uses a dedicated Dhan account funded only with the capital
allocated to the bot. Infrastructure safety is backed by financial containment.

## The private operator control room

XenAlgo has a FastAPI-based web console. It is designed as a practical supervision panel,
not a public consumer website.

The console can show:

- portfolio summary and positions;
- orders and confirmed fills;
- active circuit breakers;
- configuration summary;
- audit history;
- per-strategy learning and review information;
- authenticated kill and rearm controls.

The page uses Server-Sent Events (SSE) to push updates without requiring the operator to
refresh constantly.

## How network routing and access work

The current paper server does not expose its dashboard to the public internet.

```text
Founder’s Windows laptop
        |
        | encrypted Tailscale network
        v
Personal tailnet owned by subhamjena.j@gmail.com
        |
        v
Oracle VM: xenalso-vnic (100.120.219.15)
        |
        v
XenAlgo console on port 8080
```

The server’s public network interface remains in a restricted firewall zone with SSH only.
The private `tailscale0` interface has access to the console. We verified that the laptop
could reach the private health endpoint while the public IP could not reach port 8080.

This gives the founder a private control room without operating a public login page that
attackers can scan continuously.

## Hosting strategy

XenAlgo uses a two-stage hosting plan.

### Development and paper trading

The current host is Oracle Cloud in Mumbai:

- Oracle Linux 9;
- `VM.Standard.E2.1.Micro`;
- 1 GB RAM with additional persistent swap;
- Docker for a reproducible application image;
- systemd for startup and automatic restart;
- firewalld for network isolation;
- Tailscale for private console access.

The deployment was recovered and completed on 11 July 2026 after the original 1 GB VM ran
out of memory during package installation. The bootstrap now creates swap before heavy
package work so the same failure is less likely on a fresh host.

### Real-money hosting

The plan does not rely on a free VM once real capital is involved. Before live trading, the
same Docker image will move to a paid India-region VPS, such as AWS Mumbai or DigitalOcean
Bangalore.

The live host requires reserved primary and secondary public IPs registered with Dhan at
least seven days before go-live. Oracle remains a paper, development and warm-staging box.

This creates portability: the application does not need to be rewritten for the live host;
the same verified image is redeployed into more reliable infrastructure.

## How data is stored

### DuckDB for market and research data

DuckDB stores daily price and volume history used by research and strategy calculations. The
live design uses one controlled writer for nightly ingestion and read-only access elsewhere.

### SQLite for orders, controls and audit history

SQLite runs in WAL mode with full synchronization for the order journal, derived state,
risk state and audit log. It is intentionally simple: this is a single-user system handling
dozens of meaningful events per day, not millions of consumer transactions.

### Backups

The target operating model includes nightly SQLite backups, market-data export, off-box
object storage, VPS snapshots and monthly restore drills. Backup scripts and real restore
evidence remain part of the pre-live operational gates.

## What has been built across the project

### Research foundation

- The original backtest and research engine was preserved.
- Three validated strategies were promoted without casually rewriting their logic.
- An offline walk-forward validation harness was added to test behaviour across time splits.

### Paper execution core

- Append-only order journal and replayable state.
- Order lifecycle and confirmed-fill accounting.
- Pure, independently tested RiskEngine.
- Order-rate governor.
- PaperBroker and broker interface contracts.
- Fill listener, reconciliation and kill-switch behaviour.
- Data-freshness, price-sanity, scheduler and clock-skew guards.
- Capital sleeve isolation and paper-day orchestration components.

### Operator console

- FastAPI console with health, snapshot, configuration and learning endpoints.
- SSE state updates.
- Authenticated kill and rearm controls.
- Telegram command routing.
- HMAC-validated postback scaffolding, kept disabled until public ingress is reviewed.

### Failure and safety testing

- Unit, integration, contract, property and chaos tests.
- Scenarios include duplicate fills, crash recovery, token expiry, corrupted candles,
  reconciliation drift, rejection storms, network problems and clock skew.
- The local suite currently passes 114 tests.
- The deployed Oracle image passed 113 tests with one optional local-snapshot skip.
- The host chaos selection passed all 9 tests.

### Evidence gates

The repository contains conservative evaluators for the four-week paper burn-in, paid
live-host readiness, post-migration paper validation, first 10% activation checklist, and
the staged 10%, 25%, 50% and 100% capital ramp.

These tools check evidence. They do not pretend calendar time or live operation happened.

### Learning layer

The project contains a controlled learning scaffold that can analyze trade history and
produce parameter-change proposals. Proposals remain pending until a human approves or
rejects them. The learning layer cannot silently rewrite live risk limits.

## What is working today

As of 11 July 2026:

- the repository’s full local test suite is green;
- the Oracle paper VM is running;
- Docker and systemd deployment are working;
- the private Tailscale route is working;
- the console health endpoint is reachable privately;
- public port 8080 is refused;
- the authenticated paper kill/rearm control is proven over the private network;
- live trading is disabled;
- the Dhan order API is disabled;
- the public postback endpoint is disabled;
- required credential fields exist on the host without being committed to Git.

## What is not yet complete

This distinction matters in an investor discussion.

The deployed service currently runs the operator console. The repository has tested
paper-execution components and an integration-level `PaperDayRunner`, but it does not yet
have the scheduled production paper daemon required to run all three strategies unattended
on live market data every trading day.

Therefore, the real four-week paper burn-in has **not started**.

Remaining milestones include:

1. Build and verify the scheduled, data-only production paper daemon using `PaperBroker`.
2. Run at least four calendar weeks of paper trading on live market data.
3. Review each strategy sleeve against its backtest expectations every trading day.
4. Configure off-box backups, external heartbeat and restore-drill evidence.
5. Choose and provision the paid India-region live host.
6. Register static IPs with Dhan and wait the required lead time.
7. Run at least one further week of paper validation on the paid host.
8. Complete the go-live checklist and receive explicit operator approval.
9. Start with no more than 10% of allocated capital.
10. Move through 25%, 50% and 100% only after at least two clean weeks at every stage.

There is intentionally no production live-order Dhan gateway enabled today.

## The investor-friendly roadmap

### Stage 1: Prove the machine without money

Finish the production paper daemon and run it on the existing Oracle host. Demonstrate
reliable daily operation, private supervision, accurate journaling and clean reconciliation.

### Stage 2: Prove durability over time

Complete the four-week burn-in. Measure uptime, token refresh, deviations from the research
model, safety incidents and unexplained outliers.

### Stage 3: Move to production infrastructure

Deploy the same container to a paid India-region VPS, configure reserved IPs, backups,
heartbeat monitoring and restore procedures, and run another paper-validation week.

### Stage 4: Introduce capital gradually

After every mandatory gate passes, activate only 10% of the allocated capital. Increase to
25%, 50% and finally 100% only after clean evidence at every stage.

### Stage 5: Improve with controlled learning

Use accumulated trade history to identify slippage, regime changes and weakening strategy
behaviour. The software may recommend changes; the founder remains the final approver.

## How to present XenAlgo to an investor

### A short founder speech

> XenAlgo is an autonomous swing-trading platform for Indian equities, built around three
> validated strategies. Our key differentiation is not just the signal—it is the safety and
> operating system around the signal. Every proposed trade goes through an independent risk
> veto, every order is recorded before submission, positions change only on confirmed broker
> fills, and the system continuously reconciles its records with the broker.
>
> The owner supervises the bot through a private Tailscale control room rather than a public
> dashboard. We have deployed that control plane on an Oracle Mumbai server, proven that the
> public trading console is closed, and activated the emergency paper kill switch from a
> Windows laptop in 333 milliseconds. The codebase has a green automated test suite,
> including failure-injection tests designed around real trading-system disasters.
>
> We are deliberately not presenting it as live-ready today. The next milestone is the
> scheduled production paper daemon, followed by a four-week live-market paper burn-in. Real
> capital moves only after a paid-host migration, static-IP registration, backup and restore
> proof, another paper-validation week, and an explicit go-live review. Capital then enters
> in controlled stages from 10% to 100%.
>
> In simple terms, we are building a trading bot that treats reliability, auditability and
> loss containment as first-class product features—not as fixes added after money is at risk.

### The honest investment thesis

The opportunity is to turn validated quantitative research into a dependable operating
system for one controlled trading account. The defensible asset is not one formula alone. It
is the combination of strategy research, execution discipline, independent risk vetoes,
replayable operational data, private founder controls, failure testing, a measured
paper-to-live process, and a learning system that proposes rather than silently changes risk.

### What not to claim

Do not tell an investor that XenAlgo is already trading real money, has completed its burn-in,
or has proven live profitability. Those claims are not currently true.

Do not promise guaranteed returns. Historical evidence cannot guarantee future performance.

The credible statement is:

> The research and safety foundation is built, the private control infrastructure is
> deployed, and the project is entering the production paper-operation stage before any
> controlled live-capital rollout.

## Closing summary

XenAlgo is best understood as two products working together:

1. a quantitative portfolio engine that decides what it would like to own; and
2. a safety and operations platform that decides whether, when and how those decisions can
   become real broker actions.

The project’s philosophy is simple: missing one trade is acceptable; losing control of the
system is not.
