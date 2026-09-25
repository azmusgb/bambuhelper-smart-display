# UI Critique — 2026-09-25

Full external critique of the OS12 UI, captured for future work.
Current state: 8/10 visually. Main gap is hierarchy, not styling.

## What's working (do not change)
- Bottom 4-item nav (Home · Printer · Tools · Settings)
- Dark theme palette discipline
- Touch target sizes
- Wizard-style screens (34–44)

## P0 — highest impact, lowest risk
1. Reduce neutral card-border visibility 30–40%
2. Remove decorative status dots from category headers
3. Increase muted text contrast slightly
4. Normalize bottom Back/Next navigation
5. Convert option labels from ALL CAPS → Title Case

## P1 — architecture
6. Collapse 14 Display categories into 4–5 groups
7. Visible section grouping in settings
8. Simplify Custom dashboard
9. Add 1–2 live metrics to Home

## P2 — polish
10. Standardize typography tokens
11. Standardize semantic accent colors
12. Rewrite implementation-flavored copy
13. Normalize card padding
14. Audit inactive-nav contrast on physical LCD

## Design direction
Content > value > state should dominate. Less visible structure.
