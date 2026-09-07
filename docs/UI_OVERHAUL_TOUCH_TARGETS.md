# v11.25 touch target rules

Reference landscape size: 480×320.

- Routine controls: >= 48 px high/wide where the axis is actionable.
- Primary actions: target 52–60 px where layout allows.
- Persistent bottom navigation: four equal destinations with a full-cell hit region; icon/label are presentation only, not separate targets.
- Do not create sub-44 px controls to gain visual density.
- Keep at least 6 px visual separation between adjacent high-consequence controls.
- Guarded destructive controls must not share an ambiguous hit boundary with a routine action.
- Tap is the ordinary activation gesture.
- Hold is reserved for guarded/destructive/commit operations and must show progress/feedback.
