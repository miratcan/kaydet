# Kaydet Specifications

Formal specifications for kaydet's data formats and protocols. Any
conforming implementation (Python, Rust, etc.) MUST pass the test
fixtures included with each spec.

## Status Lifecycle

- **Draft** — under active development, may change without notice
- **Review** — feature-complete, open for feedback
- **Frozen** — stable, breaking changes require a new major version

## Specifications

| Spec | Version | Status | Description |
|------|---------|--------|-------------|
| [encryption](v1/encryption.md) | 1.0 | Frozen | Secret encryption wire format (scrypt + AES-256-GCM) |
| [file-format](v1/file-format.md) | 1.0 | Frozen | Day file and entry format |
| sync-protocol | — | Planned | Sync protocol messages and behavior |

## Fixtures

Test vectors live in `v1/fixtures/`. Each spec references its fixture file.
Implementations SHOULD run these fixtures as part of their test suite.

## Versioning

Specs use semantic versioning:

- **Major** (v1 -> v2): breaking change, old implementations cannot
  read new data
- **Minor** (v1.0 -> v1.1): backward-compatible addition
- **Patch** (v1.0.0 -> v1.0.1): clarification, no behavior change
