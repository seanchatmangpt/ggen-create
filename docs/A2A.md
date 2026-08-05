# A2A Service

## Profile

- Protocol profile: `1.0`
- Binding: JSON-RPC
- Discovery: `/.well-known/agent-card.json`
- Endpoint: `/a2a`
- Entry point: `ggen-create-a2a` or `ggen-create a2a serve`

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

Messages may carry structured `operation`, `arguments`, and `confirm` data. Text-only messages are routed deterministically to a bounded skill.

Every request creates a durable receiver-owned task beneath `.ggen-create/tasks/a2a/`. Successful consequences are returned as JSON and text artifact parts.

## Safety

The built-in HTTP server is unauthenticated and therefore binds only to loopback addresses. Non-loopback hosts are refused with `A2A_NON_LOOPBACK_REFUSED`.

Production exposure requires a separately admitted authenticated transport or reverse proxy. The built-in server makes no production-security claim.

Write operations still require explicit confirmation and cross the same Broker boundary used by the CLI and MCP server.
