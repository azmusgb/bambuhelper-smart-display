# Repository hygiene

The current candidate branch intentionally retains the incremental `apply_smart_home_*.py` patches and `.bambuhelper-validation/` payloads because exact-head CI uses them to reconstruct the validated firmware stack from the pinned upstream baseline.

Do not commit generated PlatformIO output, local ZIPs, temporary artifact folders, or ad-hoc validation reports to the repository root. Candidate binaries belong in GitHub Actions artifacts until promoted into the accepted download channel.
