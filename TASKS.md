# Milestone checklist

The requirements and priorities in [PROJECTS.md](PROJECTS.md) remain authoritative.
This checklist records the SMAP scope decision; it does not change other milestones.

## Backend scientific corrections

- [x] Continuous fixed-capacity daily water balance, explicit drainage and tested mass conservation.
- [x] Chronological crop sequence, autumn-to-harvest wheat, independent equally weighted starting phases and common initialization.
- [x] Remove water-free cover variants from scored recommendations; retain explicit insufficient-alternatives results for mandatory unsupported crops.
- [x] Enforce required/avoided crops, equipment, stored minimum gaps and calendar compatibility; preserve original baseline.
- [x] Nonnegative Hargreaves with explicit radiation-unit conversion; essential weather/date validation and no missing-delta substitution.
- [x] Connect both historical decades and model-specific future runs; document necessary frontend API changes and remove survival claims.
- [x] Complete and verify the exact 2031–2050 NEX cache for all 12 anchors and three models; older caches retained, with explicit unavailable-data behavior tested.
- [x] Run final scientific, API and data-preservation checks: 73 tests pass; all-anchor/four-soil historical physical checks and all-anchor/three-model future smoke checks pass.
- [ ] Future scientific refinement: defensible bare-soil/offseason evaporation, snow/frozen-soil treatment, Ontario calendar/compatibility citations and cover-crop demand inputs.
- [x] Minimal daily Blind Spots API: existing diagnostic flags, consecutive exposure events, per-phase/model counts and explicit delta-weather/approximate-screening labels. Contract: [BLIND_SPOTS_API.md](backend/BLIND_SPOTS_API.md).
- [ ] Protective ground-cover and rainfall-exposure parameters/contract remain deferred; no erosion or crop-damage claims.

Current method and frontend migration notes: [SCIENTIFIC_VALIDITY.md](backend/SCIENTIFIC_VALIDITY.md).

## SMAP — optional post-MVP observational cross-check (deferred)

Implementation, tests, technical documentation and pilot are preserved on
`origin/smap`, commit [`2e03043`](https://github.com/Nav2607/NASA_Space_Hackathon/tree/2e03043). They are not part of
the current backend branch. Existing local intermediate caches remain intact and ignored.

- [x] Retain the existing extraction pipeline, offline cache loader, dependencies, tests and [technical documentation](https://github.com/Nav2607/NASA_Space_Hackathon/tree/2e03043/backend/SMAP_SETUP.md).
- [x] Preserve the successfully retrieved [Guelph pilot](https://github.com/Nav2607/NASA_Space_Hackathon/tree/2e03043/backend/data/anchors/guelph/smap.json): 2016-01-01, eight valid samples for each moisture variable, plus existing intermediate samples.
- [x] Remove SMAP from MVP/P1 implementation work and document the deferral.
- [x] Keep SMAP extraction dependencies separate from the core backend; allow test discovery without those optional packages.
- [x] On the preserved SMAP branch, verify the optional loader works without SMAP data and without third-party packages; preserve the Guelph pilot unchanged.
- [x] Before the SMAP commit, check staged filenames and contents for authentication files and credential material; retain SMAP-specific authentication ignore rules on that branch.
- [ ] Post-MVP only, with separately agreed scope: independently review the pilot and assess a regional observational cross-check. This is not validation of hypothetical crop rotations or farm-level measurements.

Current constraint: no additional SMAP downloads and no SMAP integration into the
simulation or recommendation engine. Keep raw volumetric moisture separate from
plant-available water storage and bucket initialization. No further SMAP work is
required for the MVP; all other project requirements remain in force.
