# TradePilot AI

> **Every setup comes with its evidence.**

**Status:** Research foundation implemented through Phase 4.5 Step 2
**Product:** Evidence-based forex research and trading decision-support SaaS  
**Initial audience:** Beginner and intermediate forex traders  
**Initial markets:** EUR/USD and GBP/USD, H1 candles  
**Execution:** Research and paper trading only; **no live broker order placement** in v1

## Current implementation

The `research/` Python workspace currently includes canonical H1 bid/ask data
models, provider-neutral ingestion, OANDA and offline Dukascopy adapters,
immutable Parquet snapshots, integrity and session-gap auditing, EMA/RSI/ATR,
versioned breakout and pullback candidate detection, immutable candidate
reports, deterministic event-driven simulation, accounting, chronological
60/20/20 validation, walk-forward and cost-stress tooling, and locked-test
governance. Real-data access remains credential- or file-gated, and no result is
presented as evidence of profitability.

Developer references:

- [Architecture](docs/architecture.md)
- [Project structure](docs/project-structure.md)
- [Data flow](docs/data-flow.md)
- [Development and command reference](docs/development.md)
- [Research workspace](research/README.md)

## 1. Purpose and product promise

TradePilot AI helps traders **discover potential forex setups, inspect historical evidence, understand invalidation and uncertainty, and calculate risk before deciding whether to trade**. It is not a signal-selling service, profit-guarantee product, or automated trading bot.

Our differentiator is **auditable evidence**, including losing trades and failed strategies. Every displayed opportunity must be linked to a **versioned, reproducible strategy**, clearly stated data and cost assumptions, and an honest validation status. A detected setup is **not** proof of profitability.

### Positioning

**Headline:** Every setup comes with its evidence.  
**Subhead:** Scan EUR/USD and GBP/USD, inspect historical performance after trading costs, and plan risk in seconds. No promises. Just evidence.

Avoid marketing claims such as "guaranteed", "winning signals", "beat the market", or claims that users will earn profits. Avoid "know the odds" unless probabilities are genuinely calibrated and validated.

## 2. User experience: four connected sections

1. **Market Scanner (core):** Lists potential breakout and EMA/RSI trend-pullback setups by pair and timeframe. Displays detection time, rule/strategy version, state (watching, triggered, invalidated, expired), evidence status, and links to the details.
2. **Trading Chart:** Interactive bid/ask-aware or appropriately labeled OHLC candles, with indicators, relevant price levels, setup conditions, invalidation levels, and timestamps. Charts must disclose the source and freshness of the price data.
3. **AI Explanation:** Explains **deterministic analysis results** in accessible language: why a setup triggered, what the historical tests showed, costs, weaknesses, and what would invalidate it. The LLM must not invent prices, indicators, probabilities, or backtest statistics. AI is an explanation layer, not the signal engine.
4. **Risk Planner:** Calculates risk budget, stop-loss distance, pip value, position size, and potential planned loss using instrument/account-currency-aware arithmetic. Disclose spreads, slippage, contract size, lot increments, and limitations; losses may exceed planned risk.

**User flow:** scanner detects a candidate -> user opens chart -> user reviews evidence and AI explanation -> user uses risk planner -> user independently decides what to do -> optionally saves a setup / subscribes to an alert. No automatic real-money execution in v1.

### Supporting capabilities

- Reproducible **strategy backtesting and validation** (the product foundation).
- Paper-trading and a transparent, append-only forward signal log.
- Dashboard and Telegram alerts (later MVP phase).
- Authentication and user preferences (only when required by the user-facing MVP).
- Trade journal, economic calendar, strategy marketplace, and broker integration are **out of scope for initial MVP**.

## 3. Initial MVP scope

| Area | Initial scope |
| --- | --- |
| Pairs | EUR/USD, GBP/USD |
| Timeframe | H1; H4 later |
| Strategies | 20-bar breakout; EMA/RSI pullback (parameterized research hypotheses, not validated edges) |
| Indicators | EMA, RSI, ATR |
| Data | Target 5+ years of H1 history with bid/ask OHLC or documented spread assumptions |
| Backtesting | Deterministic, event-driven fills with realistic costs and auditable trade logs |
| Scanner | Scheduled scan on **completed** candles, deduplicated events |
| Evidence | Out-of-sample results, expectancy in R, win rate, max drawdown, profit factor, count, uncertainty, assumptions |
| Chart | Candles, indicators, setups, invalidation |
| AI | Grounded explanation of structured research results |
| Risk | Position sizing for supported FX pairs, USD accounts initially if necessary |
| Notifications | Dashboard and Telegram in later MVP phase |
| Live execution | Explicitly excluded |
| Language | English initially; Khmer later |

## 4. Architecture and technology choices

```text
Historical / current FX data provider
          |
          v
Data ingestion + validation (Python)
          |
          v
Canonical bid/ask candles + data provenance
          |
          +------------------------------+
          |                              |
          v                              v
Indicator + strategy engine       Research backtester
(pure, deterministic rules)       (event-driven execution)
          |                              |
          v                              v
Candidate setup events           Versioned evidence reports
          |                              |
          +---------------+--------------+
                          |
                          v
                PostgreSQL persistence
                          |
                          v
                  Node.js / Express API
                     |           |
                     v           v
                 React UI     Alerts / Telegram
                     |
                     v
          AI explanations from validated facts
```

**Preferred stack** (keep optional dependencies out until needed):

- **Frontend:** React + TypeScript + Vite + Tailwind CSS; TradingView Lightweight Charts.
- **API:** Node.js + TypeScript + Express, REST; WebSocket only if real-time updates warrant it.
- **Research and scanning:** Python 3.12+, pandas, NumPy, FastAPI for service endpoints when integration begins.
- **Backtesting:** Small custom **event-driven** order/fill simulator; vectorized indicators are fine.
- **Database:** PostgreSQL; schema migrations and typed access. Prefer Prisma on the Node side if appropriate.
- **AI:** Gemini or replaceable LLM adapter, integrated **after** the deterministic engine and reports work.
- **Alerts:** Telegram Bot API; background worker/scheduler when needed.
- **DevOps:** Docker Compose for local services; CI for lint, types, tests; production deployment decisions later.

**Design principles:** separate research logic from APIs and UI; pure, testable strategy functions; deterministic results for a fixed dataset/configuration; explicit timezones (UTC), precise financial calculations, traceable data provenance, and versioned strategies/reports. Avoid microservices and infrastructure complexity without a demonstrated need.

## 5. Trading data requirements

- Research EUR/USD and GBP/USD **H1 candles** for at least five years if legally licensed, reliable data is available.
- Prefer bid and ask OHLC. If only mid OHLC is available, use a documented historical spread model and mark reports as lower-fidelity; do not imply exact fills.
- Store timestamps in UTC; define candle-open/candle-close convention; use **closed candles only** for signal generation.
- Preserve provider, retrieval time, instrument, timezone, precision, price basis, spread source, and data version/checksum.
- Validate ordering, duplicates, missing bars, impossible prices, bid <= ask, weekend/holiday gaps, DST effects, and anomalous spikes. Flag rather than silently fabricate missing data.
- Do not commit proprietary raw datasets or provider API keys. Confirm provider licensing before public redistribution or commercial use.
- Support a small **synthetic fixture dataset** for local development and tests, so Codex can work without paid credentials.

## 6. Research and backtesting specification

### 6.1 Strategies

Implement strategies as deterministic functions that accept **historical candles available up to the current decision time**, strategy parameters, and instrument metadata, and return structured candidate signals. Start with:

- **Breakout:** Prior 20 completed bars' high/low, optional EMA trend and ATR filters. Exclude the current bar from breakout reference levels.
- **EMA/RSI pullback:** Explicit trend filter, pullback condition, confirmation rule, and invalidation. Parameters must be recorded and versioned.

These are **hypotheses**, not established profitable systems. Specify long/short symmetry, entry timing, stop/target logic, maximum concurrent positions, session filters, and expiry rules before testing. Never change rules after viewing the locked test results.

### 6.2 Execution simulation

- Generate signals only after the candle is complete; **earliest market entry is the next candle's executable open**, not the signal candle close.
- Buy at ask, sell at bid. Account for spread, slippage, commissions where applicable, overnight swap/financing, and position sizing.
- Model stop-loss/take-profit triggers and gap fills. If both stop and target could trigger in the same H1 candle, use lower-timeframe data or a **documented conservative fill policy**; never assume the favorable order.
- Track cash/equity, realized/unrealized P&L, exposure, trade-level R multiples, drawdowns, and full order/fill history.
- Run sensitivity scenarios at **1x and 2x modeled trading costs**. Document assumptions and limitations.
- Write regression tests for look-ahead leakage, costs, spread-side fills, ambiguous intrabar exits, and reproducibility.

### 6.3 Validation and evidence

- Chronological split: first **60% training**, next **20% validation**, final **20% locked holdout**.
- Tune only on training/validation; use rolling **walk-forward** evaluation with strictly forward-looking test windows. Avoid data leakage in features, normalization, and parameter selection.
- Freeze code, parameters, datasets, and assumptions **before** running the locked holdout once. If it fails, record the failure; don't repeatedly tune against the same holdout.
- Report: expectancy in R/trade (net of costs), win rate, max drawdown, profit factor, number of trades, average win/loss, period covered, and a dependence-aware confidence interval (e.g., block bootstrap where appropriate).
- Roughly **100 trades** is a screening heuristic, **not** statistical proof. Report insufficient evidence where sample size, independence, or market-regime coverage is weak.
- Track all parameter variations attempted, failed experiments, and selection rationale to reduce data-snooping bias.
- **Kill criterion:** If no strategy shows positive net expectancy under **2x costs on the untouched holdout**, do **not** market it as an opportunity with a demonstrated edge. Retain the platform as a research/risk tool.
- **Forward paper testing:** Automatically timestamp and log every new signal before its outcome is known; begin with 4–8 weeks, extend until sample size and regime coverage justify conclusions. Paper results are not verified live-broker performance.

### 6.4 Evidence labels

Every displayed result must explicitly identify its category: **in-sample**, **validation**, **locked holdout**, or **forward paper test**. Show strategy version, test window, trade count, cost assumptions, and data source. Do not present an in-sample chart as a live track record. Publish failures and losing trades alongside successes.

## 7. Proposed data model (evolve via migrations)

These are conceptual entities, not a command to create every table immediately:

| Entity | Purpose |
| --- | --- |
| `instruments` | Pair, pip size, quote/base currency, contract metadata |
| `data_sources` | Provider, licensing/provenance, retrieval metadata |
| `market_candles` | Timestamped, validated bid/ask OHLC and data quality flags |
| `strategies` | Named versioned rules and parameter schemas |
| `backtest_runs` | Dataset hash, code version, parameters, cost model, split, timestamps |
| `backtest_trades` | Every simulated entry/exit/fill, fees, P&L and R |
| `research_reports` | Metrics, confidence intervals, warnings, validation labels |
| `scan_events` | Immutable candidate signals, detection time, strategy version and state |
| `paper_trades` | Forward-test events, hypothetical fills and outcomes |
| `users` | Accounts and authentication (when introduced) |
| `alerts` | User preferences, notification status, deduplication |
| `ai_explanations` | Source report IDs, model version, generated explanation |

Indexes should support `(instrument, timeframe, candle_time)` uniqueness, time-range queries, and idempotent scan events. Never overwrite historical evidence when a strategy version changes.

## 8. API contracts (planned, not implemented)

Endpoints may evolve as implementation progresses. Use validation, pagination, typed error responses, and authentication for user-specific data.

```text
GET  /api/health
GET  /api/markets/instruments
GET  /api/markets/candles?symbol=EURUSD&timeframe=H1&from=...&to=...
GET  /api/scanner/opportunities
GET  /api/scanner/opportunities/:id
GET  /api/research/strategies
GET  /api/research/reports/:id
POST /api/risk/calculate
POST /api/analysis/explain          # later; server-side LLM only
POST /api/alerts                    # later; authenticated
```

Do not expose API keys, unlicensed market data, or private trading records. Version public contracts when necessary.

## 9. Security, integrity, and compliance

- Keep provider/LLM/Telegram secrets server-side in environment variables; ship `.env.example`, never real secrets.
- Validate all inputs and authorize access to user-specific resources. Apply rate limits and audit logs as the API becomes public.
- Treat all model output as untrusted; validate structured analysis against source records and label AI explanations.
- No custody of customer funds, no broker credentials, and no live order execution in v1.
- Clearly disclose uncertainty, backtest limitations, and that historical performance does not guarantee future results.
- Review financial-advice/marketing requirements and data licensing in intended launch jurisdictions before charging users.

## 10. Repository layout (target, create incrementally)

```text
tradepilot-ai/
├── README.md
├── AGENTS.md                   # optional, add when Codex conventions are stable
├── .env.example
├── .gitignore
├── client/                     # React UI; later
├── server/                     # Node API; later
├── research/
│   ├── pyproject.toml
│   ├── src/tradepilot/
│   │   ├── data/               # providers, normalization, validation
│   │   ├── indicators/         # pure indicator calculations
│   │   ├── strategies/         # versioned signal rules
│   │   ├── backtest/           # event-driven execution
│   │   ├── validation/         # splits, walk-forward, statistics
│   │   └── reporting/          # evidence reports
│   └── tests/
├── docs/
│   ├── decisions/              # architecture decision records
│   ├── research/               # protocols and experiment logs
│   └── phases/                 # milestone acceptance records
└── compose.yaml                # only when local multi-service setup is needed
```

This is a **target layout**, not evidence that these files or modules already exist. Keep code modular but avoid empty scaffolding for future phases.

## 11. Development roadmap — one phase at a time

| Phase | Deliverable | Completion gate |
| --- | --- | --- |
| **1 — Foundation & data** | Python project, configuration, synthetic fixtures, provider adapter, data normalization/quality checks, tests | Deterministic fixture import, quality report, reproducible commands, tests passing |
| **2 — Strategies** | EMA, RSI, ATR; breakout and pullback rule implementations | No future-data access; clear unit tests and versioned parameters |
| **3 — Backtesting** | Event-driven simulator, cost model, fills, trade log | Cost/slippage/gap/intrabar test cases pass; repeatable results |
| **4 — Research validation** | 60/20/20 splits, walk-forward, locked holdout process, metrics, report artifacts | Transparent reports with uncertainty and experiment tracking |
| **5 — Scanner & API** | Completed-candle scheduled scanning, event persistence, read APIs | No duplicate or premature signals; traceable evidence links |
| **6 — Dashboard** | Scanner, chart, evidence details, risk planner | End-to-end demo using real licensed or synthetic labeled data |
| **7 — AI & alerts** | Grounded AI explanations, Telegram alerts, paper-trade logging | Factual grounding tests, deduplication, traceable alerts |
| **8 — Beta & release** | Security review, monitoring, paper validation, user interviews | Honest evidence presentation and launch readiness review |

Phases 1–4 of the Python research foundation are implemented. Later product
phases remain unauthorized until explicitly approved.

## 12. Instructions for Codex (read before every task)

1. **Read this README first** and treat it as the product source of truth unless the user explicitly changes requirements.
2. **Work on only the phase and task explicitly requested.** Never implement future phases preemptively.
3. Before coding, summarize the goal, relevant files, assumptions, and a short implementation plan. Ask for clarification only when a decision blocks correct implementation.
4. Prefer the simplest maintainable solution. Avoid unrelated refactors, speculative dependencies, paid APIs, and elaborate infrastructure.
5. Never invent historical market data, backtest performance, API credentials, or claims of profitability. Use explicitly labeled synthetic fixtures for tests and demos.
6. Build and test deterministic financial logic before adding LLMs. No LLM-generated signals, prices, fills, or performance metrics.
7. Add meaningful automated tests for every new research or financial calculation. Run relevant tests and report results; never claim a command passed if it wasn't run.
8. Preserve timestamp, provider, dataset, cost model, strategy version, and code/config hashes in research outputs wherever practical.
9. Keep secrets out of source control. Update `.env.example` and documentation when adding configuration.
10. At the end of each task, report **files changed, behavior added, commands to run, tests executed, limitations, and the next proposed task**. Stop and wait for user approval.
11. If a proposed implementation conflicts with realistic market simulation or evidence integrity, explain the issue rather than silently weakening standards.
12. Do not change the product scope, stack, or roadmap without explicit user approval.

## 13. Current maintenance milestone

Phase 4.5 improves organization and reviewability without changing research
behavior. Steps 1–2 establish architecture documentation, golden identity
regression tests, and dependency-free shared canonical serialization. Further
module moves, dependency refactors and new product features require separate
approval.

## 14. Product success criteria

We will judge the platform on **research integrity and real user value**, not on the number of generated alerts:

- Transparent, reproducible backtest reports with all losses included.
- No look-ahead bias and realistic cost/fill assumptions.
- Clear distinction between in-sample, holdout, and forward results.
- Honest handling of inconclusive or failed strategies.
- Accurate, understandable risk calculations and setup explanations.
- Beta users report meaningful time savings or improved decision discipline.
- Users demonstrate willingness to pay for the research tools **without promises of profit**.

---

**Guiding rule:** *Evidence first. Risk second. Explanation third. The trader makes the decision.*
