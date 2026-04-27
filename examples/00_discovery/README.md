# Example 00 — Discovery

Phase 1 demo. Two agents:

- **Agent B** ("CompanyB Document Agent") publishes one skill manifest (an invoice extractor) and serves it over HTTP.
- **Agent A** ("CompanyA") fetches Agent B's `/.well-known/agent.json`, then lists Agent B's manifests.

The demo uses `httpx.ASGITransport` so it runs in-process — no real port needed. The same code path works against a network-bound `uvicorn` server; only the transport changes.

## Run

```bash
uv run python -m examples.00_discovery.main
```

## Expected output

```
Discovered agent: CompanyB Document Agent
  url:                       http://companyb.test
  polypact version:          0.1
  supported transfer modes:  ['delegate', 'lease', 'compose']
  supported conformance:     [1]

Found 1 manifest(s):
  - did:web:companyB.com#extract-invoice
      name:         Invoice Field Extraction
      version:      1.2.0
      inputs:       ['document']
      outputs:      ['fields']
      pricing:      model='per_invocation' amount=0.05 currency='USD'
```

## What it demonstrates

- Conformance Level 1: agent card + manifest list/fetch over HTTP
- The Polypact extension on the A2A Agent Card (`card.polypact.*`)
- Round-trip through the JSON serializer — the manifest the client deserializes is byte-equal to what Agent B registered
