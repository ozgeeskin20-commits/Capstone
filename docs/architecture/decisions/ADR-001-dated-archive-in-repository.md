# ADR-001: Build a dated archive in the repository from automated daily collection

- **Status:** Accepted
- **Date accepted:** 2026-11-25
-  **Approval evidence:** Approved by <Furkan Alim> on 2026-11-25 via <CAPSTONE WP grubu / toplantı>.
- **Decision owner:** Furkan Alım
- **Related requirements:** REQ-001, REQ-003, REQ-005, REQ-010, REQ-013
- **Related ADRs:** None identified.
- **Related GitHub Issues:** None exists.
- **Approval evidence:** Pending. This ADR is submitted for review and is not implemented as an accepted decision.
- **Supersession references:** None.

## Context and problem statement

The collector writes each verified snapshot to `_local_data/`, which `.gitignore` excludes from version control. The repository therefore holds no historical observations. Each contributor accumulates a private and intermittent record on their own machine, determined by when they happen to run the dashboard or the collector. Those records are not shared, not reviewable, and not reproducible by another contributor.

The EPDK charging stations payload contains no installation-date field. A station's installation date can only be approximated by the first date on which its identifier appears in a dated series of observations. REQ-013 commits the project to monthly and yearly station counts and states that monthly new-installation analysis requires appropriate dated historical evidence or a validated collection methodology. REQ-003 makes the same conditional commitment for historical development analysis. Neither can currently be satisfied, and no evidence source exists that would satisfy them retroactively.

The cost of delay is not recoverable. Every day without a recorded observation is a permanent gap in the only evidence base available for these requirements.

A second, related problem: `src/auto_collector.py` triggers a live collection when no snapshot younger than the freshness threshold is present. On a hosted deployment with ephemeral storage, the local data directory is empty after each cold start, so visitor traffic would drive repeated requests to a third-party public endpoint the project does not own.

## Decision drivers

- REQ-013 and REQ-003 depend on dated evidence that does not exist today and cannot be reconstructed later.
- REQ-001 requires reproducibility: an analytical result should be verifiable by another contributor from repository contents.
- REQ-005 requires that source access methods, coverage and rights be assessed rather than assumed; the endpoint is not a documented public API and its availability is not guaranteed.
- Repository growth must stay bounded over the project's lifetime.
- The approach must not depend on a single contributor's machine being powered on.
- Personal data must not enter version control.

## Alternatives considered

**A. Status quo: local-only snapshots.** No repository growth and no new machinery. Leaves REQ-003 and REQ-013 unsatisfiable, keeps evidence private to individual machines, and continues to accrue unrecoverable gaps. Rejected on requirements grounds.

**B. Commit raw snapshots.** Maximum fidelity and no derivation to maintain. The raw payload is large, compresses to roughly one to three megabytes per day, and would add an estimated several hundred megabytes per year of binary objects that do not delta-compress. It would also place a field that can contain a natural person's name under version control. Rejected on growth and privacy grounds.

**C. Object storage via the existing S3 adapter.** `S3StorageAdapter` already exists and would hold raw snapshots without repository growth. It requires an account, credentials held as repository secrets, a billing owner, and a retention decision, and it places the evidence base outside the artefact the project submits and the jury can inspect. Not rejected on merit; deferred as a possible later addition for raw retention. It does not by itself satisfy the reproducibility driver.

**D. Derived compact archive committed to the repository, produced by scheduled collection.** Raw snapshots remain local and uncommitted. A derived record, small enough to version, is committed daily. Collection runs on GitHub's runners rather than a contributor's machine.

## Decision and rationale

Adopt alternative D.

A new module, `src/archive/daily_archive.py`, reads the snapshot that the collector's manifest points at and derives three artefacts under `data/archive/`:

- `daily/YYYY-MM-DD.csv.gz` — station-level measures for that day: socket count, AC and DC socket counts, and summed nameplate power. Measured at 62.6 KB for the 2026-11-25 snapshot of 17,265 stations.
- `stations_dim.csv` — one row per station identifier ever observed, holding slowly changing attributes together with `first_seen` and `last_seen`. Measured at 3.6 MB. Sorted by station identifier so that day-to-day differences remain small and delta-compress well; only the first commit carries its full size.
- `daily_totals.csv` — one row per day for time-series reads, carrying the snapshot identifier and checksum so that any daily figure can be traced to the verified snapshot it came from.

The split between a daily measure file and a slowly changing attribute file keeps per-day growth proportional to what actually changes rather than to the full station population.

The module reuses `src.data_loader.load_dataset` and `src.validator.validate_charging_dataset` rather than parsing the payload independently, so the archive and the dashboard cannot diverge in how a record is interpreted.

`first_seen` is the evidence REQ-013 requires. It is explicitly an observation date, not an installation date, and must be presented as such wherever it is used. The archive establishes no history before its own start date.

A scheduled GitHub Actions workflow runs the existing collector with `EPDK_COLLECTION_ENABLED=true`, builds the archive, and commits only `data/archive/` to `develop`. This removes the dependency on a contributor's machine and makes a single daily request from a single origin.

## Positive consequences

- REQ-013 and the historical aspect of REQ-003 become satisfiable from the date of acceptance onward.
- Every contributor works from the same evidence; a reviewer can reproduce a figure from repository contents.
- Collection no longer depends on any contributor's machine being powered on.
- Once the repository carries a current record, the dashboard can read it instead of calling the endpoint on cold start, reducing request volume against a third-party service.
- Daily totals carry the snapshot checksum, so a published figure can be traced to a verified snapshot.

## Negative consequences and trade-offs

- The repository grows continuously. On measured volumes this is roughly 23 MB per year from the daily files, plus the delta-compressed revisions of the 3.6 MB dimension file, and a one-off 3.6 MB on the first commit. This is a permanent commitment for the project's lifetime.
- The derived schema becomes an interface. Changing it later requires either rebuilding the archive from retained raw snapshots, which are not retained under this decision, or accepting a discontinuity in the series.
- Raw payloads are not retained beyond the latest local snapshot, so fields excluded from the derived schema cannot be recovered retrospectively. Alternative C remains available if raw retention later becomes necessary.
- A bot commit appears on `develop` each day, adding noise to the history.
- The archive's value increases with time, so its usefulness during the early project period is limited.

## Security, privacy, operational and maintenance implications

The raw payload contains `sarjIstasyonuIsletmecisi`, which can hold a natural person's name. The module removes this field before any derivation and the test suite asserts that neither the field nor its values appear in the committed archive. Only the licensed network operator's title and licence number are retained, which are corporate attributes.

No credentials are introduced. The workflow uses the repository-scoped token already provided to Actions and requires workflow permissions to be set to read and write.

Operationally, the workflow requires a single settings change and no infrastructure. GitHub disables scheduled workflows in repositories with no activity for 60 days; the daily commit ordinarily prevents this, but a dormant period would require manual re-enablement.

## Risks

- **The endpoint may be unreachable from GitHub's runners.** Not verified at the time of proposal. Mitigation: run the workflow manually once before acceptance. If it fails, a contributor continues local collection and pushes the derived archive periodically; the archive format is unaffected.
- **Access conditions may change.** The endpoint is not a documented public API. Mitigation: request data formally from EPDK, as REQ-005 contemplates; the archive already collected remains usable regardless.
- **Repository growth may exceed the measured first-day rate**, for example if the station population grows substantially or the dimension file's daily delta proves larger than expected. Mitigation: re-measure after two weeks of real data and reconsider alternative C if the observed rate materially exceeds the figures above.
- **A degraded upstream response could enter the archive.** Mitigation: the collector's existing validation threshold and read-back verification gate the snapshot before the archive reads it; the threshold should be raised from its default to a value appropriate to the observed station population.
- **`first_seen` may be misread as an installation date.** Mitigation: label it as an observation date in the data dictionary and at every point of presentation.

These risks should be reflected in the risk register if this ADR is accepted.

## Implementation implications

This ADR proposes, and does not authorize, the following: a new `src/archive/` package, a scheduled workflow under `.github/workflows/`, a new committed directory `data/archive/`, and a repository settings change granting Actions write permission. Tests accompany the module and run with the existing suite. No existing module is modified.

A separate decision, not proposed here, would change `src/auto_collector.py` to prefer the committed archive over a live request on cold start.

## History

- 2026-11-25: Drafted and submitted as Proposed. Not accepted; no implementation is authorized by this document.
- 2026-11-25: Replaced size estimates with figures measured from a local build against the 2026-11-25 snapshot (17,265 stations, 50,607 sockets, 4,049,167.62 kW). The build's station, socket and installed-power totals matched the dashboard's figures for the same snapshot.
- 2026-11-25: Accepted following explicit project-owner approval.
