# MCP Server

## Profile

- Protocol revision: `2025-11-25`
- Transport: newline-delimited JSON-RPC over stdio
- Entry point: `ggen-create-mcp --root <subject>` or `ggen-create mcp serve`

## Lifecycle

The server negotiates exactly `2025-11-25`. A client must complete:

```text
initialize request
→ initialize result
→ notifications/initialized
```

Capability use before the initialized notification is refused with `MCP_LIFECYCLE_REFUSED`. Unsupported revisions are refused during initialization. `ping` remains available for transport liveness.

## Capabilities

### Tools

Fourteen bounded tools expose:

```text
capture inspection
automatic planning and application
package-integrity verification
persistent automatic watch
single-cycle and convergent autonomic control
agent routing and dispatch
self-play
P0–P7 parity verification
receipt and receipt-chain verification
evidence-backed doctor standing
```

Tool arguments are checked against the published JSON Schemas in `tools/list`. Unknown properties, missing required properties, invalid types, and out-of-range bounds are refused mechanically.

Read tools execute immediately. Every write tool requires `confirm:true` and supports optional task-augmented execution.

### Resources

The server exposes only this allowlist:

```text
ggen-create://session
ggen-create://skills
ggen-create://agents
ggen-create://receipts/latest
ggen-create://receipts/chain
ggen-create://doctor
```

Arbitrary filesystem URI reads are not supported.

### Prompts

`create-factory`, `repair-factory`, and `certify-factory` encode inspect-before-act, integrity-aware repair, and narrow-standing doctrine. Required prompt arguments are validated.

### Tasks

Task capability must be advertised by the client during initialization before any task method or task-augmented tool call is accepted.

Task-augmented calls mint receiver-owned durable task IDs beneath `.ggen-create/tasks/mcp/`. Execution occurs in a contained worker. The server supports:

```text
tasks/get
tasks/list
tasks/result
tasks/cancel
```

Task documents carry bounded TTL and polling intervals. Terminal results include `_meta["io.modelcontextprotocol/related-task"]`. Cancelling a terminal task is refused, expired tasks are pruned, and unexpected worker exceptions terminate the task as failed rather than leaving it indefinitely working.

## Authority

MCP grants no ambient authority. Tool calls are translated into canonical skill intents. Agents may route and construct intents; only the Broker performs confirmed native DO. Both successful and blocked confirmed consequences emit chained receipts.

The original-compatible capture CLI remains a separate compatibility surface and is not silently represented as Broker-mediated native actuation.
