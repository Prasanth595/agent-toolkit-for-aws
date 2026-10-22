---
_fragment: billing
_of_phase: discover
_contributes:
  - render-resource-inventory.json
---

# Discover billing evidence

Invoke `parse-render-billing.py` through the frozen skill-local project. Use only its closed JSON user-stated/monthly-export contracts or exact CSV header. Reject unknown properties or headers before row processing, overlapping service periods, invalid dates, negative/non-decimal amounts, mixed currencies without an explicit dated conversion, and duplicate/missing conversions. Retain only aggregate Decimal arithmetic, period, currency, count, digest, and provenance—never raw rows.

If no source is present, record current spend as unavailable; never recall or invent Render prices.
