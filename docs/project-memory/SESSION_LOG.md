# Session Log

Record sessions chronologically. Include scope, changed files, checks and results, unresolved risks, and references to approved decisions or requirements. Do not record secrets or private correspondence.

## 2026-10-30 — Local project memory setup

- Scope: establish local project memory, requirement and decision governance, risk tracking and an issue register without modifying approved documents or application code.
- Baseline: clean `develop` at `5197b4656297eb0d0bf3715b1882d12e49482d03`; local `main` pointed to the same commit.
- Created: root `AGENTS.md`; five files under `docs/project-memory/`; architecture overview and ADR template; risk register; and GitHub Issue register.
- Checks: Git reported no tracked-file changes and `git diff --check` produced no output; all 10 new files passed local-link and trailing-whitespace checks. A pattern scan found no matching credential material. Application tests were not run because this task adds documentation only.
- Open risks: source access and history, external data rights, and the unconfigured private reporting channel; see [risk register](../risks/RISK_REGISTER.md).
- No commit, push or GitHub Issue is authorized by this setup task.

## 2026-11-03 — Governance hardening

- Scope: correct branch documentation, establish conflict handling and record the approved future architecture issue workflow; no architecture decisions were made.
- Changed: `AGENTS.md`, `CONTRIBUTING.md`, `docs/project-memory/PROJECT_CONTEXT.md`, `docs/project-memory/REQUIREMENTS.md`, `docs/project-memory/OPEN_QUESTIONS.md`, `docs/project-memory/SESSION_LOG.md`, and `docs/project-management/GITHUB_ISSUE_REGISTER.md`.
- Clarified: both local branches point to the initial documentation commit, `develop` is active, and [REQ-012](REQUIREMENTS.md) requires issue records after approval of the complete architecture decision set. The session originally described issue creation as requiring explicit authorization; the correction below clarifies the existing conditional authorization.
- Validation: local Markdown links, requirement IDs, ADR statuses, branch state, branch wording, issue references, sensitive-information patterns, authorized scope and whitespace were checked; see the task report for results. Application tests were not run because only governance documentation changed.
- Open: [Q-005](OPEN_QUESTIONS.md) retains the original implementation-task question and the unresolved issue grouping strategy; the architecture decision set and other existing questions remain open.

## 2026-11-03 — Governance audit corrections

- Scope: clarify ADR issue eligibility, existing conditional authorization, REQ-012 provenance and the historical Git status discrepancy; no application code or issues were created.
- Changed: `AGENTS.md`, `docs/project-management/GITHUB_ISSUE_REGISTER.md`, `docs/project-memory/REQUIREMENTS.md`, `docs/project-memory/OPEN_QUESTIONS.md` and this session log.
- Clarified: only Accepted ADRs qualify; the complete decision set and issue grouping strategy require user approval before issue creation. REQ-012 originated on 2026-10-30 and was registered on 2026-11-03.
- Git evidence: repository root and working directory are `C:\Codex`, Git directory is `C:\Codex\.git`; current status lists 10 untracked files. The user supplied a historical three-file output, while available session records also contain a ten-file status. The cause of the discrepancy is unresolved; current timestamps, index and ignore checks cannot establish the historical cause.
- Validation: Markdown links and whitespace, requirement IDs, ADR statuses, approval wording, dates and confidential-information patterns were reviewed; `git diff --check` excludes untracked files. See the task report for results and limitations. Application tests were not run for this documentation-only task.
- Open: the historical Git status discrepancy, architecture decisions and issue grouping strategy remain unresolved; see [Q-005](OPEN_QUESTIONS.md).

## 2026-11-03 — Final pre-approval documentation hardening

- Scope: document the owner's approved Core / Extended / Future planning tiers, requirements traceability, governance lifecycle, source limitations and risk management before architecture design.
- Prototype: recorded the team-reported external Colab-to-Drive proof of concept as unreviewed and not repository-integrated or selected as production architecture; no notebook was copied or integrated.
- Changed: `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, `docs/PROJECT_SCOPE.md`, `docs/DATA_SOURCES.md`, `docs/architecture/ARCHITECTURE_OVERVIEW.md`, `docs/architecture/decisions/ADR-000-TEMPLATE.md`, `docs/project-memory/README.md`, `docs/project-memory/PROJECT_CONTEXT.md`, `docs/project-memory/REQUIREMENTS.md`, `docs/project-memory/OPEN_QUESTIONS.md`, `docs/project-memory/SESSION_LOG.md` and `docs/risks/RISK_REGISTER.md`. The issue register already reflected the requested conditional workflow and was not changed.
- Validation: checked Markdown links, whitespace, unique requirement IDs, ADR status consistency, scope tiers, prototype and data limitations, issue authorization, branch policy and credential patterns; see the task report for exact results and limitations. Application tests and EPDK requests were not run for this documentation-only task.
- Open: source access, quotas, rights and historical evidence; external prototype review; architecture; other interactive analytics classification; issue grouping; private reporting channel; and the historical Git status discrepancy. See [open questions](OPEN_QUESTIONS.md).
- No commit, push or GitHub Issue was created.

## 2026-11-05 — Integration commit and remote synchronization on develop

- Scope: commit local governance, project memory, architecture templates and documentation baseline to `develop` and push to remote `origin/develop` per explicit user instruction and REQ-007.
- Baseline: local `develop` with uncommitted working tree modifications and untracked documentation files; remote `origin` empty.
- Branch policy: reaffirmed the two-branch workflow (`main` and `develop`) per REQ-007 and CONTRIBUTING.md following explicit user confirmation.
- Action: committed all modified and untracked documentation files to `develop` and pushed `develop` to `origin`.
- Validation: performed whitespace/diff checks and credential pattern scans prior to push.
- Remote synchronization: following explicit user authorization, pushed `main` (`5197b46`) to `origin/main` to complete remote baseline setup for both branches (`develop` and `main`).

## 2026-11-05 — Phase 0 closure and local MVP prototype implementation

- Scope: configure GitHub branch protections and secret scanning, implement provisional local data loader, validator, analytical metrics module, and Streamlit dashboard prototype; execute synthetic validation tests and startup smoke checks.
- GitHub Configuration: enabled secret scanning and push protection on GitHub; applied branch protection rules to `main` (require PR, block force push/deletion, enforce admins; review requirement deferred as sole collaborator) and `develop` (block force push/deletion, enforce admins, direct collaborator pushes allowed); default branch kept as `develop`.
- Implementation: built `src/data_loader.py`, `src/validator.py`, `src/metrics.py`, `app.py`, `requirements.txt`, and unit tests under `tests/`.
- Validation: 11 pytest unit tests passed; Streamlit headless smoke test succeeded (HTTP 200). No real EPDK data was available in the repository; prototype verified with synthetic fixtures and local upload flow.
- Architecture: Streamlit/pandas/Plotly stack is provisional; no permanent architecture decision has been accepted.
- No commit, push, Issue or PR was created.

## 2026-11-05 — Phase 1 real EPDK data integration and MVP verification

- Scope: integrate local EPDK archive (`epdk_raw_20261030_082729.json` and paired CSVs) located in `Google Colab Kodlar/` and `_local_data/`; configure `.env` file for credentials/endpoints; enhance loader, validator, metrics and Streamlit dashboard; run reference verification and unit tests.
- Security: created `.env` (ignored by `.gitignore`) to isolate EPDK API gateway configurations and paths; added `Google Colab Kodlar/` to `.gitignore` to prevent committing real data archives, notebook outputs, or correlation tokens; confirmed working tree is protected from credential leaks.
- Real Data Integration:
  - Source files inspected: `epdk_raw_20261030_082729.json` (17,087 stations, 49,746 sockets), `istasyonlar_20261030_082729.csv`, `soketler_20261030_082729.csv`, and `attempt_log.jsonl`.
  - Snapshot timestamp verified: `2026-10-30T08:27:29.644664+00:00`.
  - Schema mapping: mapped `sarjIstasyonuNo` -> `station_id`, `soketNo` -> `socket_id`, `sarjAgiIsletmecisiUnvan` -> `operator_name`, `soketTipi` -> `socket_type`, `soketGucu` -> `power_kw` (verified unit: kW).
- Data Quality Findings:
  - 4 licensed stations have empty socket arrays (`soketler: []`) at snapshot time; loader was updated to preserve them as registered stations without generating false socket rows.
  - 1 socket (`SKT/62480`) has conflicting classification (`soketTipi: DC` vs `soketTuru: AC_TYPE2`); flagged as conflicting classification warning in validation report.
  - 100% of socket power values are positive numbers in kW (range: 2 kW to 720 kW, mean: 79.12 kW). Total socket nameplate rating sum: 3,935,849.4 kW.
- Testing: 12 unit tests passed in pytest; Streamlit headless smoke test succeeded (HTTP 200).
- No commit, push, Issue or PR was created.

## 2026-11-05 — Phase 1.1 Complete and verify the existing MVP

- Scope: complete existing real-data MVP fixes without geographic expansion; correct metric labels; verify CSV dataset linkage (`_row_id`); clarify power unit provenance and float precision; expand unit test suite; package review zip.
- Metric label corrections:
  - Replaced "Aktif İstasyon (Soketli)" with "Soketi bulunan istasyon" across validator, tests and UI. Avoids inferring operational status from socket presence.
  - Clarified operator shares as "Soket Sayısı Payı (%)" within the selected snapshot/filter scope; explicitly disclaimed revenue, utilization, or energy-market share.
- CSV dataset linkage:
  - Verified `istasyonlar_*.csv` and `soketler_*.csv` outer join on export-local `_row_id`.
  - Preserved 4 stations without sockets (`socket_id = None`).
  - Implemented graceful handling when socket CSV is absent (displays station counts, sets socket/power metrics to `None`/`Mevcut Değil` without synthetic substitution).
  - Parity verification: raw JSON vs paired CSVs produces 100% exact parity (17,087 stations, 49,746 sockets, 4 socketless stations, 28,111 AC, 21,635 DC, total power sum `3,935,849.42`).
- Power unit analysis:
  - Investigated Swagger schemas, Colab notebooks, and EPDK raw JSON columnNames. Found zero explicit unit definitions for `soketGucu`.
  - Retained original numerical values and documented "kW" as an unverified industry assumption.
  - Preserved internal float precision (total power sum: `3,935,849.42`).
- Verification & Testing:
  - 21 unit tests passing across `tests/test_loader.py`, `tests/test_validator.py`, and `tests/test_metrics.py`.
  - Verified application startup via headless Streamlit probe (`HTTP 200 OK`).
- Review package:
  - Created `C:\Codex\_local_data\mvp_code_review.zip` strictly containing 10 files (`app.py`, `requirements.txt`, `src/` modules, `tests/` modules) with zero data records or credentials.
- Git & Boundaries:
  - Working tree remains uncommitted on `develop`.
  - No commit, push, merge, branches, Issues or PRs were created.

## 2026-11-05 — Phase 1 MVP Defect Fixes, Cloud-Ready Daily Collector, and Dashboard Integration

- Scope: resolve 5 reproduced MVP defects; build an autonomous cloud-ready daily EPDK collector with separate API client, validator, compressed storage, and manifest manager; prepare a GitHub Actions daily collection workflow (`0 6 * * *` UTC = 09:00 Europe/Istanbul); integrate S3 object storage retrieval path into Streamlit dashboard; make paths project-relative; expand test suite to 45 passing tests.
- Phase 1 Defect Fixes:
  - Defect 1 (Power filter default): Default full-range power slider no longer removes socketless stations (17,087 stations preserved in default view); station population is explicitly labeled as "Soket Kriterine Uyan İstasyonlar" when socket-level filter is active versus "Kayıtlı Tüm İstasyonlar" by default.
  - Defect 2 (AC/DC distribution & duplicates): `get_ac_dc_distribution` counts actual sockets only, excluding socketless station placeholders from being categorized as "Bilinmiyor"; duplicate socket records are consistently deduplicated across counts, distributions, and power totals.
  - Defect 3 (Operator selection): Clearing the multiselect when "Tüm Operatörleri Seç" is unchecked now produces an empty result (`0` rows).
  - Defect 4 (Index offset independence): `validate_charging_dataset` uses positional offsets during iteration, eliminating `IndexError` on non-range indexed DataFrames (`[10, 20]`).
  - Defect 5 (Upload failure stale data): Failed file uploads reset `raw_df` to `None` to prevent fallback to previously selected local data; active source is prominently displayed.
- Daily Collector Implementation:
  - `src/collector/api_client.py`: Implemented `EPDKApiClient` reusing verified Colab endpoint and request structure, with bounded exponential backoff retries, explicit timeout, and `Retry-After` parsing.
  - `src/collector/validator.py`: Implemented `CollectorValidator` separating fatal structural failures (empty/malformed response, count below threshold) from non-fatal source warnings.
  - `src/collector/storage.py`: Implemented `LocalStorageAdapter` and `S3StorageAdapter` with gzip compression, SHA-256 verification, individual snapshot metadata (`epdk_meta_*.json`), atomic `latest_manifest.json` updates, and failure logging (`collector_failure_log.jsonl`).
  - `src/collector/collector_service.py`: Orchestrated fetch-validate-compress-store lifecycle with concurrency lock protection against overlapping runs.
  - `src/collector/run_collector.py`: CLI entrypoint gated by `EPDK_COLLECTION_ENABLED` repository/environment variable.
- Provenance Binding:
  - `src/data_loader.py`: Updated to bind metadata directly to snapshot files via content hash (SHA-256), `latest_manifest.json`, individual `epdk_meta_*.json`, and exact filename timestamp pattern matching in `attempt_log.jsonl`.
- Cloud Workflow:
  - Added `.github/workflows/daily_epdk_collector.yml` scheduled at `0 6 * * *` UTC (09:00 Europe/Istanbul), with `workflow_dispatch`, read-only repository permissions, concurrency grouping, 15-minute timeout, and gated execution.
- Testing & Verification:
  - 45 automated unit, regression, execution, and mock integration tests passing in pytest (6.88s).
  - Headless execution test confirmed app startup without crashes.
- Review Archive:
  - Refreshed `_local_data/mvp_code_review.zip` containing 20 authorized reviewable files (source, tests, workflow, dependencies) with 0 credentials and 0 real datasets.
- Git & Boundaries:
  - Working tree remains uncommitted on `develop`.
  - No commit, push, merge, branch, Issue or PR was created.

## 2026-11-05 — Pre-Cloud Activation Hardening and Resolution of 7 Review Findings

- Scope: resolve 7 independently reproduced security, integrity, concurrency, and validation findings prior to cloud activation; expand automated test suite to 59 passing tests; refresh code review package.
- 1. Authoritative Disable Switch:
  - `.github/workflows/daily_epdk_collector.yml`: Gated job execution with `if: vars.EPDK_COLLECTION_ENABLED == 'true'`; removed `--force` input parameter and shell CLI flags; documented concurrency scope and cron timezone constraints.
  - `src/collector/run_collector.py`: Removed `--force` argument and CLI bypass; strictly enforces `is_collection_enabled()`.
  - `requirements.txt`: Declared `boto3>=1.34.0` cleanly without shell redirection operators (`>`).
- 2. Envelope & Completeness Validation:
  - `src/collector/validator.py`: Added HTTP/EPDK envelope checks: rejects responses with `statusCode != 200` or error payload structures; enforces exact match between declared envelope `numRows` and actual station records count; inspects every station and socket entry structurally (rejects malformed/non-dict elements). Preserves valid empty socket lists and AC/DC conflicts as warnings. Manifest remains untouched on validation failure.
- 3. Verify Stored Bytes Before Promotion:
  - `src/collector/collector_service.py`: Implemented read-back verification of stored snapshot bytes (checking both uncompressed SHA-256 content hash and byte length) before updating `latest_manifest.json`; treated manifest update failures as job aborts.
  - `src/data_loader.py`: Standardized hash semantics to uncompressed content bytes across `.json` and `.json.gz`; enforced that matching filename never overrides checksum mismatch; ensured unknown provenance remains unknown.
  - `app.py`: Integrated `verify_snapshot_integrity`; verifies downloaded cloud snapshot bytes against manifest before displaying; stops with an explicit integrity error on hash mismatch.
- 4. Collision Prevention & Concurrency Protection:
  - `src/collector/collector_service.py`: Generates collision-resistant snapshot IDs (`YYYYMMDD_HHMMSS_<hex>`); implemented atomic exclusive lock file (`open(..., 'x')`) with owner token and process cleanup.
  - `src/collector/storage.py`: Implemented create-only writes (`'xb'`, `'x'`) raising `FileExistsError` on existing target; implemented monotonic timestamp protection in `update_latest_manifest` preventing older runs from overwriting newer manifests.
- 5. Conflicting Duplicates Handling:
  - `src/metrics.py`: Separated exact duplicate rows from conflicting socket records; completely eliminated arbitrary `keep="first"` row-order dependence; implemented `detect_socket_conflicts` to identify multi-operator, multi-power, and multi-type socket conflicts; excluded unresolved values from affected aggregates with clear exclusion counts; implemented `_drop_duplicates_safe` to safely handle DataFrame deduplication in the presence of unhashable validation error lists.
- 6. Actual Application Execution & Test Suite:
  - `src/dashboard_controller.py`: Extracted core dashboard dataset filtering, verification, and file upload handlers for headless testability.
  - `tests/test_app_execution.py`: Verified app execution via headless Streamlit probe and comprehensive controller tests (synthetic fixture metrics, empty operator selection, failed upload state reset, cloud integrity-error abort).
  - Test suite expanded to 59 automated tests passing in pytest (5.90s).
- 7. Review Archive & Clean Boundaries:
  - Refreshed `_local_data/mvp_code_review.zip` strictly containing 21 clean source, test, dependency, and workflow files (0 secrets, 0 data records).
  - Git working tree remains uncommitted on `develop`; no staging, commit, push, merge, branches, Issues or PRs created.
  - No live EPDK requests or external cloud storage operations were executed.

## 2026-11-05 — API Envelope Completeness and S3 Atomic Conditional Writes Hardening

- Scope: resolve remaining API-envelope validation gaps and implement race-free atomic S3 storage operations; expand test suite to 70 passing tests; refresh review package.
- 1. Complete API Envelope Validation:
  - `src/collector/validator.py`: Rejected explicit failure indicators (`isSuccess=False`, `success=False`, `hasError=True`); rejected nonempty error fields (`error`, `errors`, `errorMessage`, `exception`); selected status code by field presence so `statusCode=0` is strictly evaluated and rejected; strictly validated declared row counts (`numRows`), supporting exact integer strings while explicitly rejecting malformed counts (`invalid`, negative, booleans) and count mismatches; preserved empty socket lists and AC/DC conflicts as non-fatal warnings.
  - Verified that envelope rejection leaves previous storage manifest completely intact and unchanged.
- 2. Atomic S3 Writes & Error Classification:
  - `src/collector/storage.py`: Eliminated `head_object` / unconditional `put_object` race conditions; snapshot and metadata creation enforce `IfNoneMatch="*"`; initial manifest creation enforces `IfNoneMatch="*"`; existing manifest updates use optimistic concurrency with `IfMatch=<current_etag>`; on 412 PreconditionFailed, bounded reread and timestamp re-evaluation is performed with zero unconditional overwrite fallback; monotonic timestamp comparison preserves the newer manifest; only genuine 404/NoSuchKey returns not-found; permission errors (403), timeouts/server errors (500), and malformed JSON are classified and propagated.
  - `requirements.txt`: Declared `boto3>=1.35.0` supporting S3 conditional PutObject parameters.
- 3. Stateful Concurrency Tests:
  - `tests/test_collector.py`: Built `StatefulFakeS3Client` enforcing S3 conditional headers and ETags; added 5 stateful race and error tests (snapshot key collision, first manifest race, newer manifest interleaving, read error propagation, and verification of zero unconditional fallback).
  - Total test suite expanded to 70 tests passing in pytest (5.52s).
- 4. Boundaries & Package:
  - Refreshed `_local_data/mvp_code_review.zip` (21 authorized files, 0 data, 0 secrets).
  - Working tree remains uncommitted on `develop`. No staging, commit, push, merge, branch, Issue or PR was created. S3 behavior verified via stateful fakes locally.

## 2026-11-24 — Automatic Data Acquisition Integration and Live EPDK Snapshot Verification

- Scope: transform dashboard from manual file/archive selector into an automatic EPDK data acquisition system; bridge collector service with Streamlit via transparent session-cached auto-collection; execute authorized live EPDK API request; verify metrics and data integrity with live dataset; package refreshed review zip.
- 1. Automatic Acquisition & App Simplification:
  - `src/auto_collector.py`: Created module managing transparent snapshot acquisition, freshness checking (24h threshold), timestamp parsing (ISO/UTC), formatting in `Europe/Istanbul` (+03:00), fallback to last successful snapshot on connection failure, and session-state friendly loading.
  - `app.py`: Removed default 3-mode radio selector and manual file upload from primary view; default flow opens directly and checks for recent snapshot or runs automatic collection; dynamic sidebar filter changes reuse cached session state without triggering re-fetch; added "🔄 Şimdi Güncelle" button for manual re-collection; relegated file upload, local archive selection, and synthetic fixtures behind an explicit "🛠️ Geliştirici Modu" toggle.
- 2. Authorized Live Collection Execution:
  - Executed live authorized EPDK API request against `https://apigateway.epdk.gov.tr/sarjIstasyonlari`.
  - Live result: snapshot `20261124_112635_9d0f9e` collected and persisted to `_local_data/epdk_raw_20261124_112635_9d0f9e.json.gz`.
  - Live counts: 17,259 registered stations, 50,587 sockets (100% with sockets, 0 socketless in current live snapshot), 1 socket AC/DC classification warning preserved.
  - Read-back verification passed (SHA-256: `ba96926f560976dbe0c6129c3bc4313f5c01d9b98b319e1dbcfb5bd50486d257`, raw size: 16,239,198 bytes, compressed size: 1,399,421 bytes).
  - Manifest promoted atomically to `_local_data/latest_manifest.json`.
- 3. Testing & Verification:
  - Added `tests/test_auto_collector.py` covering timestamp parsing, Istanbul timezone formatting, freshness thresholds, and fallback on failure.
  - Total test suite expanded to 75 automated tests passing in pytest (7.61s).
  - Verified live dataset metrics: 17,259 stations, 50,587 sockets, 2.93 sockets/station, 4,046,102.62 kW total nameplate socket power, 28,474 AC sockets, 22,113 DC sockets, 174 licensed operators.
- 4. Boundaries & Package:
  - Refreshed `_local_data/mvp_code_review.zip` (23 authorized clean files, 0 credentials, 0 real data records).
  - Git working tree remains uncommitted on `develop`; no staging, commit, push, merge, branches, Issues or PRs created. Cloud schedule remains unactivated pending user direction.

## 2026-11-24 — Phase 1.2.2 Performance Vectorization, Strict AC/DC Reconciliation, and UI Refinements

- Scope: resolve main thread CPU bottleneck; replace iterative loops with vectorization; implement deterministic same-row AC/DC conflict classification; enforce strict reconciliation equation; update terminology and unverified power labels; cache validated data per snapshot; expand regression tests to 78 passing tests; refresh code review package.
- 1. Performance Vectorization & Caching:
  - `src/validator.py`: Completely vectorized `validate_charging_dataset`; replaced `iterrows()` with vectorized Series masks and numpy `flatnonzero` for error formatting. Execution time dropped from 5.62s to 0.38s (15x speedup).
  - `src/metrics.py`: Vectorized `get_ac_dc_distribution`; eliminated per-socket Python loop over 50,587 groups, dropping duration from 17.53s to 0.34s (50x speedup).
  - `app.py`: Implemented session-state caching for `validated_df` and `summary` bound to snapshot ID / content hash + `VALIDATION_VERSION` (`v1.2.2`). Warm filter interactions execute in 0.008s (3,400x speedup). Total cold start reduced from ~28s to 3.11s.
- 2. AC/DC Conflict Classification & Reconciliation:
  - Centralized single-row conflict detection (`soketTipi=DC` vs `soketTuru=AC_TYPE2`) into `socket_type_normalized = "Çelişkili"`.
  - Reconciled category counts: Total Sockets (50,587) = AC (28,474) + DC (22,112) + Çelişkili (1) + Bilinmeyen (0).
  - Preserved valid power (22.0) of type-conflicting socket in overall sum while isolating it in the "Çelişkili" category in AC/DC power charts.
- 3. Terminology & Power Standardization:
  - Corrected subtitle to "Kayıtlı Şarj Soketleri" (removed "Aktif Şarj Uçları").
  - Formatted power card label as "Toplam Soket Güç Değeri" with footnote explicitly stating source unit is unverified (industry assumption: kW) and no physical MW conversions are performed.
- 4. Verification & Testing:
  - Added regression tests in `test_metrics.py`, `test_validator.py`, and `test_app_regression.py`.
  - Test suite expanded to 78 passing tests (`pytest -q -p no:cacheprovider` -> 78 passed in 8.92s).
  - `git diff --check` clean. Working tree remains uncommitted on `develop`. Review archive refreshed (23 files).


## 2026-11-25 — Dated archive and repository-served dashboard

- Scope: establish a shared dated observation series and remove the dashboard's live call on cold start. Two decisions were proposed, approved by the project owner and implemented on `develop`.
- Problem: collected snapshots remained in `_local_data/`, which `.gitignore` excludes, so no shared dated history accumulated and [REQ-013](REQUIREMENTS.md) could not be satisfied. The gap is not recoverable retrospectively.
- Decisions: [ADR-001](../architecture/decisions/ADR-001-dated-archive-in-repository.md) records the dated archive and scheduled collection; [ADR-002](../architecture/decisions/ADR-002-dashboard-reads-repository-snapshot.md) records serving the dashboard from the committed snapshot. Both are Accepted.
- Added: `src/archive/__init__.py`, `src/archive/daily_archive.py`, `src/archive/repo_snapshot.py`, `tests/test_daily_archive.py`, `tests/test_repo_snapshot.py`, `.github/workflows/daily-archive.yml`, and the committed directories `data/archive/` and `data/current/`.
- Changed: `src/auto_collector.py` gained a repository-snapshot step and a shared fallback helper; `app.py` gained a source label for it. The collector, the storage adapters and the dated archive were not modified.
- Checks: the full test suite passed, including 18 new tests. The scheduled workflow ran successfully and committed the first archive record, confirming that GitHub runners can reach the endpoint; the fallback in ADR-001 was not required. With `_local_data/` removed, the dashboard served the repository snapshot without a live request and reported 17,265 stations, 50,607 sockets and 4,049,167.62 kW, matching a live collection.
- Measured: daily archive file 62.6 KB; `stations_dim.csv` 3.6 MB; `sockets_latest.csv` 6.58 MB.
- Open: the dated series begins on 2026-11-25 and establishes no earlier history. The daily delta of `data/current/sockets_latest.csv` is not yet observed and should be re-measured after two weeks. The risks recorded in ADR-001 and ADR-002 are not yet reflected in the [risk register](../risks/RISK_REGISTER.md). Analysis work has not started.