# Domain Docs

How engineering skills should consume this repository's domain documentation.

## Before exploring, read these

- `CONTEXT.md` at the repository root, or `CONTEXT-MAP.md` when it exists.
- Relevant ADRs under `docs/adr/`.

If a referenced document does not exist, proceed silently.

## File structure

This is a single-context repository:

```
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

Use terms defined in `CONTEXT.md` in issues, proposals, tests, and other engineering output. If output conflicts with an ADR, surface the conflict explicitly rather than silently overriding it.
