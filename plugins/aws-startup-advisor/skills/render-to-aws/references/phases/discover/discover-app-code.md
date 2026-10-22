---
_fragment: app-code
_of_phase: discover
_contributes:
  - render-resource-inventory.json
  - { file: ai-workload-profile.json, _when: "provider-neutral AI evidence reaches the documented threshold" }
  - { file: render-ai-discovery.json, _when: "provider-neutral AI evidence reaches the documented threshold" }
---

# Discover application evidence

Invoke `scan-render-application.py` through the frozen skill-local project. Traverse bytewise without VCS-ignore dependence and inspect only the closed source, manifest, Dockerfile, and Procfile set. Skip symlinks, secret-named, generated, dependency, binary, oversized, raced, or root-escaping files and record metadata-only skip reasons. Never execute source.

Record content fingerprints and safe infrastructure/process symbols without snippets. Environment-variable names may be evidence; values may not. AI evidence is scored from known dependencies, imports, SDK construction, calls, endpoints, frameworks, and names. At score 70 or greater with SDK construction or method-call evidence, emit two artifacts from the same scan. `ai-workload-profile.json` conforms to the shared #415 contract: providers are `openai`, `anthropic`, or `google` with a `source_service` (`openai_api`, `azure_openai`, `anthropic_api`, `gemini_api`, `vertex_ai`); OpenRouter appears only as a gateway (`product: openrouter`, `type: llm_router`) with observed or unresolved upstreams, never as a provider; each source carries explicit `model_evidence`; every evidence entry has provenance `code`, a `confirmed` or `medium` confidence, and a `path:line` detail. `render-ai-discovery.json` is the Render-internal graph with deterministic identities and complete reachability. Neither artifact carries an execution block; the deferral state is recorded in `ai_track`.
