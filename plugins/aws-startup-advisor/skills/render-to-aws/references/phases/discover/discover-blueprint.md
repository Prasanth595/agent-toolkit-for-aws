---
_fragment: blueprint
_of_phase: discover
_contributes:
  - render-resource-inventory.json
  - render-resource-clusters.json
---

# Discover from Render Blueprint

Invoke `parse-render-blueprint.py` through the frozen runtime with absolute source, workspace-root, migration-dir, and output paths. Structural validation against the pinned official schema occurs before any normalization. Semantic evidence is current only when `outcome` is `valid`, errors are empty, the normalized source path and digest match, and its manifest identity digest plus attempt/workspace/consent tuple match the active capture manifest. Local broken references and explicitly invalid semantic evidence block canonical normalization. Absent or stale semantic evidence remains recorded as requiring renewed consent but does not block Blueprint-only Discover; when the Blueprint contributes to the inventory, it blocks Generate until the main window obtains current digest-bound validation. Accept only `BLUEPRINT_OK`; otherwise stop this contribution. Preserve the source digest, placements, canonical identities, references, controls, and sanitized validation state. Never persist literal environment values.
