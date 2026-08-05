# MCP Server

## Profile

- Protocol revision: `2025-11-25`
- Transport: newline-delimited JSON-RPC over stdio
- Entry point: `ggen-create-mcp --root <subject>` or `ggen-create mcp serve`

## Lifecycle

The server implements `initialize`, `notifications/initialized`, and `ping`. Calls before initialization are refused.

## Capabilities

### Tools

Nine bounded tools expose capture inspection, automatic planning/apply, autonomic convergence, agent routing/dispatch, self-play, parity verification, and receipt verification.

Read tools execute immediately. Every write tool declares task support and requires `confirm:true`.

### Resources

The server exposes only an allowlist:

```text
ggen-create://session
ggen-create://skills
ggen-create://agents
ggen-create://receipts/latest
```

Arbitrary filesystem URI reads are not supported.

### Prompts

`create-factory`, `repair-factory`, and `certify-factory` encode the inspect-before-act and narrow-standing doctrine.

### Tasks

Task-augmented tool calls mint receiver-owned durable task IDs. The server supports get, list, result, and cancel operations. Task state is persisted beneath `.ggen-create/tasks/mcp/`.

## Safety

MCP does not grant ambient authority. Tool calls are translated into canonical skill intents. Agents may route and construct intents; the Broker performs confirmed DO and emits receipts.
