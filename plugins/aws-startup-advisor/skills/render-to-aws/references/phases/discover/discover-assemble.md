---
_assemble: assemble-discovery
_of_phase: discover
_reads:
  - blueprint
  - live
  - app-code
  - billing
_produces:
  - render-resource-inventory.json
  - render-resource-clusters.json
  - { file: ai-workload-profile.json, _when: "provider-neutral AI evidence reaches the documented threshold" }
  - { file: render-ai-discovery.json, _when: "provider-neutral AI evidence reaches the documented threshold" }
---

# Assemble discovery

Invoke `normalize-render-capture.py` through the frozen skill-local project. It accepts only manifest-listed files whose digests match. Live manifests additionally require active attempt/workspace/consent/ownership bindings; local-only manifests require a deterministic local identity, null Render workspace/consent/ownership fields, and no CLI/REST captures. Reconcile additive producers with field-specific precedence: REST then CLI live state for current operational configuration, Blueprint for declared repository/build/topology intent, application evidence for safe inference, metrics for utilization, and billing for current spend. Record every disagreement in `drift[]` with both values/sources, the winner, and the stable precedence reason.

Preserve transport absence, Postgres/Key Value shape differences, disk non-inference, serving versus newest deploy, cron build versus run, instance/cold-wake state, and metric outcomes. Promote populated Build Sources and immutable artifacts with service, production, and environment-promotion edges. Keep Workflow, version, task, run, and attempt identities distinct and never infer an unobserved current version.

Apply the NFC/SHA-256 algorithms in `deterministic-identities.md`. Reject normalized duplicates and collisions, byte-sort every unordered collection, require closed edge kinds, and account for every resource in exactly one cluster or the explicit unclustered list. When the application capture carries AI output, pass both `--output-ai-profile` and `--output-ai-discovery`; the normalizer validates `ai-workload-profile.json` against the vendored shared #415 contract and `render-ai-discovery.json` against `schema-render-ai-discovery.json` before replacing artifacts. The `ai_track.profile_digest` recorded at Clarify is the SHA-256 of the exact bytes written to `ai-workload-profile.json`. Re-read artifacts before the main-window completion gate.
