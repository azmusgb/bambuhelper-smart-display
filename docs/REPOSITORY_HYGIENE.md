# Repository hygiene

The current candidate branch intentionally retains the incremental `apply_smart_home_*.py` patches and `.bambuhelper-validation/` payloads because exact-head CI uses them to reconstruct the validated firmware stack from the pinned upstream baseline.

Do not commit generated PlatformIO output, local ZIPs, temporary artifact folders, or ad-hoc validation reports to the repository root. Candidate binaries belong in GitHub Actions artifacts until promoted into the accepted download channel.

## Firmware retention

The Git repository is not the long-term firmware archive. Keep only:

- the currently accepted production Full + OTA binaries; and
- one immediately previous, physically accepted Full + OTA rollback pair.

Older firmware generations remain recoverable through Git history and release provenance and should not stay duplicated as tracked multi-megabyte binaries. When a new candidate is accepted, promote its production assets, retain the immediately previous accepted release as rollback, and remove older binary generations in the same release-maintenance change.
