# ADR-002: Serve the dashboard from a repository snapshot instead of a live call

- **Status:** Proposed
- **Date proposed:** 2026-11-25
- **Date accepted:** Pending explicit project-owner approval.
- **Decision owner:** Furkan Alım
- **Related requirements:** REQ-001, REQ-004, REQ-005
- **Related ADRs:** ADR-001, which established the archive and explicitly deferred this decision.
- **Related GitHub Issues:** None exists.
- **Approval evidence:** Pending. This ADR is submitted for review and is not implemented as an accepted decision.
- **Supersession references:** None.

## Context and problem statement

`run_auto_collection` serves the dashboard from the local data directory when it holds a snapshot younger than the freshness threshold, and otherwise collects from the EPDK endpoint. On a contributor's own machine this is sound: the directory persists, so at most one request is made per day.

It does not hold on a hosted deployment. Hosting platforms for this kind of application restart the process when the application wakes from idle, and the local data directory starts empty each time. Every cold start would therefore issue its own collection against a third-party endpoint that the project does not own, that it reaches through an undocumented interface, and that has already been observed returning HTTP 429 under repeated requests. Request volume would scale with visits rather than with days, which is exactly the pattern a rate limit is meant to suppress. The risk is that the project loses access to its only data source at the point where it starts sharing the dashboard.

Since ADR-001, the repository carries a verified daily observation. The data needed to render the dashboard is therefore already present in every clone and every deployment, and the live call on cold start is no longer necessary.

A second problem follows from the same gap. A figure shown on the dashboard today cannot currently be reproduced by a reviewer, because the snapshot it came from exists only on the machine that rendered it.

## Decision drivers

- REQ-005 requires that source access conditions be respected rather than assumed. Request volume proportional to visits is not a defensible use of an undocumented public endpoint.
- REQ-004 requires an interactive dashboard; it should open quickly and predictably rather than waiting on a network call.
- REQ-001 requires reproducibility: what the dashboard displays should be traceable to a verified, shared artefact.
- The change must not remove the ability to collect on demand, which remains necessary for local development and for the "Şimdi Güncelle" control.

## Alternatives considered

**A. Status quo.** No change. Leaves request volume proportional to visits, keeps cold starts slow, and leaves displayed figures unreproducible. Rejected.

**B. Lengthen the freshness threshold.** Reduces requests on a persistent machine but does nothing for a cold start, where the directory is empty regardless of the threshold. Rejected as not addressing the problem.

**C. Commit the raw payload and have the dashboard read that.** Requires no new derivation and the loader already reads the raw gzipped form. The raw payload is large, does not delta-compress, and contains a field that can hold a natural person's name. Rejected for the reasons recorded in ADR-001.

**D. Commit a socket-level current snapshot and read it before calling the endpoint.** Adopted below.

## Decision and rationale

Adopt alternative D.

The scheduled workflow writes two further files, overwriting them each day:

- `data/current/sockets_latest.csv` — socket-level rows in the project's canonical column names, uncompressed and sorted by station and socket identifier. Measured at 6.58 MB for the 2026-11-25 snapshot of 50,607 sockets.
- `data/current/manifest.json` — provenance for that file: collection time, originating snapshot identifier, source checksum and expected row counts.

`run_auto_collection` gains a step between the local-snapshot check and the live collection: if the repository snapshot is within the freshness threshold, it is served. The existing local snapshot still takes precedence when present, since it is at least as recent. `force_refresh` continues to bypass both, so "Şimdi Güncelle" still collects. The fallback paths after a failed collection now also consider the repository snapshot, so a contributor with no local data and no connectivity still sees data rather than an error.

Three choices are worth recording. The file is written uncompressed because a sorted text file delta-compresses between daily revisions, while a gzipped file does not; this keeps the repository's growth proportional to what changed rather than to the file's size. The columns are the project's canonical names, so reloading through `load_dataset` needs no renaming and the dashboard receives the same frame it would receive from the raw payload; a test asserts that the reported KPIs survive the round trip. The manifest stores no absolute path, because each clone sits at a different location; the path is resolved at read time.

Address and coordinate fields are not carried, because no current view uses them and `data/archive/stations_dim.csv` already holds them per station. Should a map view be added, that is a deliberate extension of the schema rather than an accident.

## Positive consequences

- Request volume against the endpoint becomes one per day from one origin, independent of how many people open the dashboard.
- Cold starts render from a local file rather than waiting on a network call.
- A displayed figure can be traced to a committed file and a snapshot checksum, so a reviewer can reproduce it.
- A contributor who has just cloned the repository sees data immediately, without collecting anything.
- The dashboard degrades sensibly offline, serving the repository snapshot with a staleness warning instead of an error.

## Negative consequences and trade-offs

- `data/current/` is a second committed representation of data that also exists in `data/archive/`, at a different grain. The two are written by the same code path from the same snapshot, but they remain two things to keep consistent.
- The snapshot's schema becomes an interface between the workflow and the dashboard. Adding a column the dashboard needs requires a workflow run before the dashboard can rely on it.
- The repository grows by the daily delta of a 6.58 MB text file, plus that figure once on the first commit. Sorting keeps the daily delta proportional to how much the station population actually changed, but the delta is not zero and accumulates for the project's lifetime.
- The dashboard's displayed data is up to a day old by design. This is already true of the existing freshness threshold, but it becomes the normal case rather than the exception, and the interface must say so plainly.
- One further daily bot commit touches `data/current/`.

## Security, privacy, operational and maintenance implications

The written columns carry no field that can hold a natural person's name; `sarjIstasyonuIsletmecisi` is excluded upstream by the archive builder and is not among the snapshot's columns. Only the licensed operator's title and licence number are present, which are corporate attributes.

No credentials are introduced and no new infrastructure is required. If the scheduled workflow stops running, the repository snapshot ages; the dashboard then falls through to a live collection exactly as it does today, and displays a staleness warning when it serves an old file.

## Risks

- **The repository snapshot could silently go stale** if the workflow fails unnoticed, leaving the dashboard showing old data. Mitigation: the interface labels the source and its timestamp, and warns when the snapshot is beyond the freshness threshold. A failing scheduled workflow is also visible in the Actions tab.
- **Growth from the daily file could exceed expectations.** The file's own size is measured; its daily delta is not yet observed. Mitigation: re-measure the repository's packed size after two weeks. If the rate is material, drop the operator title and station name from the file and join them from `data/archive/stations_dim.csv` at read time, which removes most of the per-row bytes.
- **The schema could drift from what the dashboard expects.** Mitigation: the round-trip test asserts that the KPIs computed after reload match those computed before writing.
- **Readers could mistake the current snapshot for a historical series.** Mitigation: the file is documented, in the module and in the manifest, as the current observation only, with the dated series in `data/archive/`.

## Implementation implications

This ADR proposes, and does not authorize: a new module `src/archive/repo_snapshot.py`; a call to it from the archive builder; a new step and a shared fallback helper in `src/auto_collector.py`; a source label in `app.py`; a new committed directory `data/current/`; and the workflow committing that directory. Tests accompany the change and run with the existing suite.

No change is proposed to the collector, to the storage adapters, or to the dated archive.

## History

- 2026-11-25: Drafted and submitted as Proposed. Not accepted; no implementation is authorized by this document.
- 2026-11-25: Verified locally against the 2026-11-25 snapshot. With the local data directory removed, the dashboard served the repository snapshot without contacting the endpoint and reported 17,265 stations, 50,607 sockets and 4,049,167.6 kW, matching the figures it reports from a live collection. Recorded the measured file size. The existing test suite passed unchanged.
