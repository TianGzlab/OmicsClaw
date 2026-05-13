# Delete the dead `MessageBus` + middleware pipeline; channels keep their direct path to `core.llm_tool_loop`

## Status

Accepted (2026-05-13).

## Context

`bot/channels/bus.py` defines `MessageBus` with `publish_inbound` /
`consume_inbound` queues. `bot/channels/middleware.py` defines a
`MiddlewarePipeline` (`AllowList` / `RateLimit` / `Audit` / `Dedup` /
`TextLimit`). `bot/run.py:_build_middleware` wires the pipeline into
`ChannelManager(bus=…, middleware=…)`, which in turn runs a
`_consumer_loop` that reads from the bus, applies inbound middleware,
calls `core.llm_tool_loop`, applies outbound middleware, and publishes
to the outbound bus for a dispatcher task.

A May 2026 audit (verified at HEAD = `e59f89d`) found the entire chain
unreachable in production:

- `grep -rn "publish_inbound" bot/ omicsclaw/` returns only the
  definition site and a docstring example. **No `Channel` subclass
  pushes a message into the bus.**
- Real channels (`bot/channels/telegram.py:464`,
  `bot/channels/feishu.py:760`, others) call `core.llm_tool_loop`
  directly from their platform handlers, bypassing the bus entirely.
- Without producers, `manager._consumer_loop` blocks forever on the
  `consume_inbound()` await, so middleware never executes.
- `RateLimit`, `Audit`, `Dedup`, etc. that *do* run in production are
  invoked directly from `bot/core.py` and `bot/rate_limit.py`,
  duplicating the dead middleware classes by name and intent.

`omicsclaw/app/server.py:4753-4814` (the `/bridge/start` endpoint)
amplifies the problem: it `from bot.run import _build_middleware`,
constructs the same dead pipeline, and threads it into a
`ChannelManager` that the desktop App spawns over HTTP. The dead chain
is therefore wired in two places but exercised in zero.

`SPEC.md` mandates: *"Do not add fallback paths or backward-compatibility
shims unless the user, public API, or repository contract requires
them."* The bus + middleware are speculative infrastructure that no
caller required. Keeping them costs review attention on every PR
touching `bot/channels/` and blocks the Phase 1 P0-A boundary work
because the reverse `omicsclaw → bot` imports in `app/server.py` are
predominantly the middleware-construction lines.

## Decision

Delete `MessageBus`, `MiddlewarePipeline`, the entire middleware module,
`_build_middleware`, and the consumer/dispatcher loops. Keep
`ChannelManager` as a thin lifecycle manager (register / start_all /
stop_all / health) with no bus, no middleware. Channels retain their
direct call path into `core.llm_tool_loop`.

The four reverse imports in `omicsclaw/app/server.py` collapse with the
deletion: `/bridge/start` constructs `ChannelManager()` with no
middleware argument and calls `start_all()`.

## Considered Options

- **Option A (chosen): delete.** Simplest. Removes ~600 LOC across
  `bus.py`, `middleware.py`, the consumer/dispatcher half of
  `manager.py`, and the `/bridge/start` wiring. The four `omicsclaw →
  bot` reverse imports in `app/server.py` disappear as a side effect.
  Closes Phase 1 P0-A. The interception concerns the dead middleware
  *would* have served (rate-limit, dedup, audit, text-limit, allow-list)
  are already implemented elsewhere on the live path.

- **Option B (rejected): wire 9 channels through the bus.** Forces every
  channel (telegram, feishu, slack, dingtalk, discord, wechat, email,
  qq, imessage) to push to `bus.publish_inbound` instead of calling
  `core.llm_tool_loop` directly. In exchange, rate-limit / billing /
  audit / dedup currently scattered through `bot/core.py` could
  centralise in middleware. **Rejected** because the centralisation
  benefit is undermined by the same audit (per-chat state already lives
  in module-level dicts that the actor refactor — Phase 2 — will fix
  with a different abstraction); and because the change touches 9
  channels at once, which violates the "smallest clear change" rule.

- **Option C (rejected): leave as-is, document as known dead code.**
  Rejected because the dead chain is the dominant source of `omicsclaw
  → bot` reverse imports, blocking the Phase 1 boundary work that
  `docs/adr/0001-bot-core-decomposition.md` already committed to.

## Consequences

- ~600 LOC deleted; no behaviour change for any channel in production.
- `ChannelManager` becomes a single-responsibility lifecycle manager
  (register + start/stop). Future "channel × cross-cutting concern"
  needs (e.g. global allow-list) will be added per-channel or via a
  decorator on the channel's handler — *not* by re-introducing a
  pipeline.
- `omicsclaw/app/server.py:/bridge/start` loses its `from bot.run import
  _build_middleware` and three sibling reverse imports, dropping the
  reverse-import allowlist count from 16 to 12 ahead of Phase 1 P0-D.
- The `bot/billing.py`, `bot/rate_limit.py`, and `bot/core.py` audit
  hooks remain the canonical implementations for those concerns. Phase
  2 will revisit their concurrency-safety story (per-chat actor /
  store), but that work is independent of bus deletion.
- If a future requirement needs a unified inbound interception point
  (e.g. for offline queueing or for shared throttling across channels),
  reintroduce a focused queue at that time with a real producer — *not*
  a generic middleware framework on speculation.
