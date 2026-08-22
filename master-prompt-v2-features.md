# Master Prompt — SourceLedger v2 Feature Build

You are extending an existing, working system. Before writing or changing any code, read, in full, in this order:

1. `docs/architecture.md` — current agents, data model, tech stack, design tokens. This is what already exists — do not re-architect it.
2. `docs/prd.md` — original MVP scope and phases (0–6). These are done; do not re-litigate them.
3. `docs/master-agent-prompt.md` — the standing operating rules and UI direction. These still apply in full and are not superseded by anything below.
4. `docs/feature-roadmap-v2.md` — the new feature phases (7–11, core) plus Phase 12 (stretch/optional) you are building now.

## Non-negotiable rules for this build

- **No hardcoded or placeholder values, anywhere, ever.** Every field, dashboard number, graph edge, or UI
  value must come from a real extraction, a real computed aggregate, or be explicit `null` +
  `needs_review`. Before marking anything done, run the anti-hardcoding check defined in
  `feature-roadmap-v2.md` ("Cross-Phase: Anti-Hardcoding Enforcement") against real batch output — not
  synthetic/sample data you constructed to pass the check.
- **Same visual system, no exceptions.** Reuse the existing Tailwind tokens (`#F5E9D8`, `#E8622C`,
  `#191715`), the existing confidence color coding, and the existing Field Inspector / Review Queue
  component patterns for any new UI. If a new screen (dashboard, graph view) is needed, it must look like it
  shipped with the rest of the app on day one — same spacing scale, same typography, one accent color used
  the same way it already is. Do not introduce a new palette, gradient, or component library.
- **Extend existing agents/files by name — don't rename or duplicate.** `IngestionAgent`, `ExtractionAgent`,
  `EnrichmentAgent`, `ValidationAgent`, `ExplainabilityLayer`, `CSVProcessor`, `KeyRotator` keep their names
  and responsibilities. New logic (conflict resolution, graph relationships, VLM routing, active learning,
  dashboard) is added inside or alongside these per `feature-roadmap-v2.md`'s specific file/module guidance —
  not as a parallel system.
- **Build in the order given in `feature-roadmap-v2.md`'s "Suggested Build Order,"** and do not start a
  phase until the previous one's Definition of Done checklist is fully satisfied and verified against real
  data, not assumed.
- **Phase 12 is stretch/optional and gated.** Do not touch any Phase 12 item until every Phase 7–11
  Definition of Done is met and verified. If time runs out before Phase 12, that is a correct outcome, not a
  shortfall — do not skip ahead into Phase 12 items to "show more features" at the expense of an incomplete
  core phase.
- **Every phase's Definition of Done is a hard gate, not a suggestion.** If a checklist item can't be
  verified, the phase is not done — flag it rather than moving on.
- If anything in `feature-roadmap-v2.md` seems to conflict with the existing architecture or the MVP
  boundaries in `prd.md`, stop and flag it rather than silently resolving the conflict yourself.

Work through `feature-roadmap-v2.md` phase by phase now, starting with Phase 7.
