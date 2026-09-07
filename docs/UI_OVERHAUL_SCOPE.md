# v11.25 screen scope

Primary 480×320 surfaces in scope:

- Home
- Printer — Status
- Printer — AMS
- Printer — Control
- Workshop
- More
- System summary
- shared header / cards / status rail / action buttons / persistent navigation
- loading / offline / disabled / warning / destructive visual states on the above surfaces

Preserved specialist flows that receive regression validation rather than semantic redesign in this slice:

- Network / Locale / Layout Expert
- Display rotation guarded preview/commit
- recovery and authenticated portal boundaries
- printer command transport and existing safety guards

The overhaul may restyle entry points into those specialist flows, but must not weaken their staged/guarded behavior.
