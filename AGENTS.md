# AGENTS.md — Field Shift Canada

## Project authority

Read `PROJECTS.md` before making changes. It is the agreed v5 specification. This is a 16-working-hour NASA Space Apps prototype, not a production agronomy platform. Preserve Southern Ontario coverage and prioritize the Climate Time Machine, Climate Blind Spots and climate-resilient adaptations.

## Working rules

- Inspect the existing repository, current branch, and relevant code before editing. Respect teammates' changes and existing conventions. Do not overwrite unrelated work.
- Work on one requested milestone at a time. Prefer simple, readable code and minimal dependencies. Do not introduce additional features or redesign the application without approval.
- Keep Python for offline data preparation and JavaScript for the single personalized simulation engine, as specified in `PROJECTS.md`. If existing architecture conflicts, report it and ask before changing stacks or implementing a duplicate engine.
- Agree on JSON contracts before parallel frontend/backend integration. Keep cached data and metadata consistent. Do not require live NASA calls for the demo.
- SMAP is an independent, optional post-MVP stretch goal for a regional observational cross-check. Its scripts, tests, documentation and Guelph pilot are preserved separately on `origin/smap`, commit `2e03043`; do not restore them onto the backend branch for the MVP. Do not initiate additional SMAP downloads or integrate it into simulation or recommendation logic. Core operation and core test discovery must work without SMAP data or extraction dependencies; on the preserved SMAP branch, keep those dependencies in `backend/requirements-smap.txt` only.
- Do not commit, push, merge, deploy, or change branches unless explicitly requested. Never expose credentials, tokens or Earthdata login details. Use ignored local environment files if necessary.

## Scientific integrity

- Never invent NASA data, crop coefficients, soil capacities, agronomic rules, observational evidence or simulation results. Record source links, units, assumptions and data quality. Unknown values remain null; missing essential inputs mean insufficient data.
- Verify actual dataset access and schemas; documentation alone is not evidence of a successful pull. Test future projections early and use the documented labeled sensitivity fallback if blocked. Never pass mock or synthetic data off as NASA data.
- Align dates and units, handle calendars and missing sentinels explicitly, and never sum POWER and GPM precipitation. Preserve climate model and scenario identity.
- Use a consistent ET0 method for historical and future simulations. Keep water calculations physically bounded, mass-conserving and continuous across rotations; document initialization, offseason evaporation and winter precipitation. Cover crops contribute to water demand without double counting.
- Use all starting rotation phases and common periods. Evaluate climate models separately before summarizing outcomes. Do not interpret model agreement as probability or projected sequences as forecasts.
- Distinguish potential water demand, actual modeled ET, shortfall and stress. Do not reward stress-induced low water use. Rainfall exposure is not erosion; nitrogen ratings are ordinal; satellite comparisons are not field validation.
- Disclose regional resolution, cross-product comparison limitations and material assumptions in the evidence panel. Do not claim measured water savings, fertilizer reductions, yield or proven field impact.

## Implementation priorities

For the current user-requested scientific correction, retain and repair the
existing Python/FastAPI engine; do not create a second engine or migrate stacks.
Use continuous chronological rotations, all starting phases, exact climate
periods and independent model runs. The implementation contract and known
process omissions are in `backend/SCIENTIFIC_VALIDITY.md`.

1. Test POWER, GPM and NEX extraction; freeze data contracts and anchor coverage.
2. Cache environmental inputs and populate cited agricultural tables.
3. Implement and test ET0, water balance, crop calendars, stress and cover/exposure.
4. Implement feasible rotation generation, scoring and model-level summaries.
5. Integrate the map, farm profile, Time Machine, Blind Spots and comparison cards.
6. Add evidence and tests; implement P1 features only once P0 works.

Follow the cut order and hour-13 feature freeze in `PROJECTS.md`. Prefer fewer supported alternatives over scientifically unfair comparisons. If blocked, state the blocker and propose the simplest transparent fallback.

## Testing and reporting

- Add focused tests for every new scientific calculation and recommendation rule. At minimum cover data units/dates/missing values, ET0, storage bounds, mass balance, nonnegative shortfall, year carryover, winter wheat, cover overlap, rotation phases, constraints, zero baseline and independent model runs.
- Run relevant existing tests and smoke checks after edits. Use the repository's established test framework; if none exists, introduce a minimal one appropriate to the language.
- Keep mock fixtures clearly labeled and separate from real data. Do not ship mock results as real demo outcomes.
- Maintain a concise `TASKS.md` milestone checklist if useful; distinguish completed, pending and blocked work.
- At the end of each task, report files changed, implementation choices, exact checks actually run and their results, remaining limitations, and the next recommended milestone. Never claim tests passed or data was verified unless actually checked.
