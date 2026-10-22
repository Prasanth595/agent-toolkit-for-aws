---
_fragment: infra
_of_phase: design
_contributes:
  - aws-design.json
---

# Design infrastructure

Load the matching design reference for every inventory kind and execute its selector in declared order. The candidate set is closed by that reference; model knowledge may not add a target. Emit one mapping per source resource, including topology-only resources consumed by another mapping. Each mapping carries:

- one nonempty `aws_service` and optional selected service configuration;
- `decision.selector`, ordered `evidence`, `rules_evaluated`, `rules_fired`, `questions_asked`, and `defaults_used`;
- one rejected-candidate row for every nonwinner in the applicable candidate set, with a rule- and resource-specific reason;
- a confidence of `deterministic`, `measured`, `inferred`, or `billing_inferred`;
- one accounting disposition and rationale.

Use the compute management-model rubric rather than source/image alone. A continuous worker selects an ECS/Fargate service; finite work selects one task target. Cron selects EventBridge Scheduler and one target. PostgreSQL, Key Value, persistent disks, Workflow orchestrators, and Workflow task classes each select one target. Static sites, environment groups/isolation, Build Sources/artifacts, domains/TLS, preview behavior, and observability follow deterministic or conditional references.

AI infrastructure remains in ordinary mappings. If the profile exists, add only the exact `deferred_shared_ai_engine` object bound to its path, the SHA-256 digest of the exact bytes of `ai-workload-profile.json`, reason, resume path, and `infrastructure_status: completed`. Do not add AI service, model, price, adapter, or Terraform fields.
