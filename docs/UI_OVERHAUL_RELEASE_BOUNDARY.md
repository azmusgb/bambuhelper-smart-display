# v11.25 release boundary

v11.25 is a stacked candidate on exact v11.23 RC2 head `44fc462dae77f6ac13809fa4c464bbe93662ab24`.

This is deliberate: the full-device overhaul needs the v11.23 touch/network/layout work as its implementation baseline, but it does **not** promote or retroactively accept v11.23.

Until the real WS350 acceptance pass succeeds:

- v11.23 RC2 remains unmerged/unaccepted.
- v11.25 remains draft/stacked and must not be promoted to stable.
- v11.24 Audio Console PR #77 remains a separate draft track and is not folded into the UI overhaul simply to avoid version/branch complexity.
- automated build/test evidence may advance v11.25 only through `tested`.

The final integration plan must preserve a linear accepted ancestry before stable promotion.
