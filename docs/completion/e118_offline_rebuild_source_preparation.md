# E118 - Offline package rebuild source preparation

Date: 2026-11-10 (Asia/Calcutta)

Branch: `p12-preparation`

Source base: `cd62b5e28c6694b4f468f9f3e033ba2377eebc61`; includes E117 changes

Status: **CODE PREPARED ONLY - BUILDER NOT RUN**

## Source changes

`build_release.py` now supports `--offline-inputs` pointing to an extracted
prior candidate. Before creating a build output directory or invoking the .NET
SDK, it requires a clean tracked source tree and verifies every listed
candidate file against `SHA256SUMS.txt`; it also checks that the candidate was
built from the same source commit. This rejects invalid offline input without
launching the .NET SDK version query. The builder then records the exact source
commit and Python/pip/.NET toolchain versions, checks that the extracted Python
wheelhouse exactly matches its hash lock, and resolves Python packages only
from the retained wheelhouse. Offline mode requires the recorded Python, pip and
.NET SDK versions to match the current builder before creating output; it does
not silently relabel a build made with a different toolchain as reproducible.

For WinUI, the builder copies the retained NuGet lock file and restores in
locked mode from a local package feed with no remote source. Newly produced
candidates retain NuGet `.nupkg` files in their hierarchical package ID/version
layout so the local feed can be consumed on a later offline rebuild. The
candidate also includes the exact Python build-support constraints, source
commit/toolchain provenance and wheelhouse hashes. Normal online candidate
creation remains available.

README documents the optional offline rebuild command. No dependency or
application runtime was added or started.

## Review and limits

This was a static source change only. The exact Windows x64 builder, `pip`,
`.NET` restore/publish, local NuGet feed, candidate archive, and offline rebuild
were not executed. The current or earlier E116 candidate lacks E118's newly
required retained Python build-constraints file and hierarchical NuGet feed;
it cannot serve as an E118 offline input. A fresh candidate must first be built
after this source is committed, then extracted and rebuilt with network access
disabled before offline reproducibility is claimed.

P28 remains open: signing is not implemented because the authorized certificate
and signing route are unavailable, and the actual package, signature, launch,
resource and policy checks have not run. This packet does not complete P28 or
authorize P29-P33 acceptance or main integration.
