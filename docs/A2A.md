# A2A Service

## Profile

- Protocol profile: `1.0`
- Binding: JSON-RPC over HTTP
- Discovery: `/.well-known/agent-card.json`
- Endpoint: `/a2a`
- Entry point: `ggen-create-a2a` or `ggen-create a2a serve`

## HTTP contract

A2A requests must send:

```text
Content-Type: application/json
A2A-Version: 1.0
```

A missing version header is interpreted as the older 0.3 profile and refused. The built-in server rejects unsupported versions, malformed JSON, non-object JSON-RPC payloads, non-JSON content types, and request bodies larger than 1 MiB.

The Agent Card is cacheable with an ETag and a bounded max-age. Conditional requests receive `304 Not Modified` when appropriate.

## Agent Card

The public Agent Card projects the nine bounded create-time roles:

```text
receiver
correspondence-analyst
manufacturing-architect
verification-architect
skill-architect
topology-architect
admission-referee
adversarial-verifier
certifier
```

The card is a projection of the canonical agent graph. It does not grant execution authority.

## Operations

The JSON-RPC service implements:

```text
SendMessage
GetTask
ListTasks
CancelTask
```

Messages may carry structured `operation`, `arguments`, and `confirm` data. Text-only messages are routed deterministically to the complete canonical skill graph.

Every accepted message creates or resumes a durable receiver-owned task beneath `.ggen-create/tasks/a2a/`. Task retrieval supports bounded history. Task listing supports status and context filtering plus cursor pagination.

## Interruption and continuation

An unconfirmed write operation does not fail or actuate. It transitions the task to:

```text
TASK_STATE_INPUT_REQUIRED
```

The caller continues the same task by sending another `SendMessage` containing the task ID, matching context, and the missing confirmation or argument. The runtime merges bounded arguments, records both messages in history, and resumes the task. Operation or context drift is refused.

All typed and unexpected execution failures terminate the durable task as failed. A task is never left working merely because session resolution, skill lookup, or execution failed.

## Artifacts

Completed consequences are returned as both structured JSON and rendered text artifact parts. Task status includes the receiver-owned context, update timestamp, task kind, TTL, and polling metadata.

## Safety

The built-in HTTP server is unauthenticated and therefore binds only to loopback addresses. Non-loopback hosts are refused with `A2A_NON_LOOPBACK_REFUSED`.

Production exposure requires a separately admitted authenticated transport or reverse proxy. The built-in server makes no production-security claim.

Write operations still require explicit confirmation and cross the same Broker boundary used by the native CLI and MCP server.
