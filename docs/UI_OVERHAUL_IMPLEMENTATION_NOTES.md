# v11.25 UI overhaul implementation sequencing

The implementation branch intentionally starts from exact v11.23 RC2 head `44fc462dae77f6ac13809fa4c464bbe93662ab24` rather than from `main` so the full-device visual pass preserves the already-tested RC2 Network / Locale / Layout behavior while it is still awaiting physical promotion.

Implementation sequence:

1. Reconstruct exact v11.23 RC2 source from the pinned upstream baseline.
2. Snapshot the generated physical UI source for inspection before replacing primary renderers.
3. Add one coherent v11.25 applicator instead of parallel ad-hoc screen implementations.
4. Replace primary Home / Printer / Workshop / More renderers and shared visual grammar while preserving authoritative device-state/control code.
5. Add explicit Printer STATUS / AMS / CONTROL navigation without inventing inventory identity.
6. Keep existing guarded Stop, power, portal-auth, Network Expert and rotation safety boundaries.
7. Add deterministic source validators and native WS350 + shared-target regression builds.
8. Capture full and OTA artifacts with exact candidate SHA and hashes.
9. Require physical WS350 acceptance before promotion.
