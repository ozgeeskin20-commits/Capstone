# Requirements Register

Each user requirement receives a unique, stable `REQ-NNN` identifier. Confirmed means explicitly requested or approved by the user; it does not mean implemented. Proposed requirements await user confirmation, assumptions are unverified and rejected requirements are not authorized. Record the source, status and changes; retain prior wording and status in a dated history entry instead of silently deleting records. Never promote an assumption to confirmed without explicit confirmation. Link relevant ADRs and actual GitHub Issues when they exist.

The entries below summarize explicit project-owner requests and the approved documentation baseline. Grouped entries preserve related requests without asserting implementation.

| ID | Status | Requirement | Source / trace |
| --- | --- | --- | --- |
| REQ-001 | Confirmed | Develop a reliable, reproducible and maintainable data collection, processing, analytics and decision-support platform for Türkiye's EV charging market. | Project owner's initial project information; [scope](../PROJECT_SCOPE.md). |
| REQ-002 | Confirmed | Provide province and district infrastructure analysis, AC/DC socket distribution, installed capacity, connectors and technical standards analysis. | Project owner's initial objectives; [scope](../PROJECT_SCOPE.md). Planned, not implemented. |
| REQ-003 | Confirmed | Compare licensed operators and market shares, and analyze historical development and monthly new installations when suitable evidence exists. | Project owner's objectives and data limitations; [data sources](../DATA_SOURCES.md). Planned, not implemented. |
| REQ-004 | Confirmed | Provide interactive analytics, dashboards and professional market intelligence reports. | Project owner's initial objectives; [scope](../PROJECT_SCOPE.md). Planned, not implemented. |
| REQ-005 | Confirmed | Consider EPDK market statistics, SAİ license list and charging stations API as planned sources; investigate availability, fields, historical coverage and rights before relying on them. | Project owner's documentation hardening request; [data sources](../DATA_SOURCES.md). No integration exists. |
| REQ-006 | Confirmed | Preserve the public PolyForm Noncommercial 1.0.0 licensing strategy and third-party rights; commercial permission may be granted separately in writing by relevant copyright holders. | Project owner's licensing policy; [LICENSE](../../LICENSE), [NOTICE](../../NOTICE). |
| REQ-007 | Confirmed | Use `develop` for development and integration and `main` for stable releases; do not create other branches; promote reviewed releases from `develop` to `main`. | Project owner's workflow clarification; [contribution guide](../../CONTRIBUTING.md). |
| REQ-008 | Confirmed | Maintain project memory, numbered requirements, ADR governance, risk and actual GitHub Issue registers, and a chronological session log. | Project owner's local project memory and governance request. |
| REQ-009 | Confirmed | Before implementation review project instructions, memory, relevant requirements and ADRs, branch and working tree, and identify scope; after tasks run appropriate checks and report results, risks and session summary. | Project owner's working protocol. |
| REQ-010 | Confirmed | Do not accept an ADR without explicit user approval, convert an assumption into a confirmed requirement, publish secrets, automatically commit, push or create GitHub Issues; obtain approval before publishing to GitHub. | Project owner's governance and working protocol. |
| REQ-011 | Confirmed | Use EVCify only as a high-level benchmark; do not copy its code, branding, proprietary designs, assets or text. | Project owner's initial project information; [product reference](../PRODUCT_REFERENCE.md). |
| REQ-012 | Confirmed | After the complete architecture decision set has been reviewed and approved by the user, record all accepted architectural decisions in GitHub Issues. | Project owner's instruction of 2026-10-30, formally registered on 2026-11-03; grouping remains unresolved in [Q-005](OPEN_QUESTIONS.md). |
| REQ-013 | Confirmed | Analyze monthly and yearly charging station counts; monthly new-installation analysis requires appropriate dated historical evidence or a validated collection methodology. | Project owner's approved 2026-11-03 core classification; related to REQ-003; see traceability clarification below and [data limitations](../DATA_SOURCES.md). |
| REQ-014 | Confirmed | Analyze power-class distribution and compare charging network operators by installed power. | Project owner's approved 2026-11-03 core classification; related to REQ-002 and REQ-003; see traceability clarification below. |

## Scope tiers and decision links

The owner approved the Core / Extended / Future planning classification on 2026-11-03. Core receives first implementation priority; extended features are not prerequisites for the initial core product. Existing grouped requirements remain intact and may span tiers. Governance and cross-cutting constraints apply across tiers, not as product feature priorities. No specific future features are approved. No project-specific ADR exists; related ADRs for all entries are therefore none yet.

| Requirement | Scope tier | Mapping and trace |
| --- | --- | --- |
| REQ-001 | Core / cross-cutting | Core collection and decision support; reliability and maintainability apply across tiers. |
| REQ-002 | Core / Extended | Installed capacity is Core; province, district, AC/DC, connectors and standards are Extended. |
| REQ-003 | Core / Extended / review | Monthly new installations relate to Core REQ-013, subject to evidence; operator market share is Extended. Other historical development analysis remains for review. |
| REQ-004 | Core / Extended | Interactive dashboard is Core; professional reports are Extended. Other interactive analytics not specifically classified require review. |
| REQ-005 | Core / cross-cutting | EPDK-based collection is Core; source investigation and rights apply across tiers. The individual source categories remain planned, not verified integrations. |
| REQ-006–REQ-012 | Cross-cutting governance | Licensing, workflow, memory, review, issue and benchmark constraints apply across tiers. |
| REQ-013 | Core | Separately confirmed monthly and yearly station counts; extends the monthly-installation aspect of REQ-003. |
| REQ-014 | Core | Power-class distribution and operator comparison by installed power; related to REQ-002 and REQ-003. |

The initial project-owner requests and approved baseline are the source of REQ-001–REQ-012 as recorded above. The owner reports an original Siemens request, but the available evidence does not map specific features to Siemens; team enhancements and the owner's later classification are distinct. Do not infer Siemens attribution.

REQ-013 details the monthly new-installation aspect of REQ-003 and adds the owner's later approved monthly and yearly station-count scope. REQ-003 does not explicitly specify those station counts, so REQ-013 is not wholly a decomposition of its wording. REQ-014 relates to REQ-002's installed-capacity analysis and REQ-003's operator comparison; power-class distribution and comparison by installed power are specified by the owner's later approved scope rather than explicitly stated in either earlier requirement.

## Proposed, assumed and rejected requirements

No additional requirement has been recorded in these categories. Open questions and assumptions are tracked separately in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

## Change history

- 2026-10-30: Initial register created from the project owner's requests and approved documentation baseline; no existing requirement was changed or removed.
- 2026-11-03: Added REQ-012 from the project owner's explicit governance hardening request; issue grouping remains unresolved.
- 2026-11-03: Corrected REQ-012 provenance: the original conditional instruction was given on 2026-10-30 and formally registered on 2026-11-03. The earlier history entry is retained; the grouping strategy also requires approval before issue creation. The existing conditional instruction supplies authorization once its conditions are satisfied, consistent with REQ-010's approval requirement.
- 2026-11-03: Recorded the owner's approved scope tier mapping without renumbering or changing prior requirement wording. Added REQ-013 and REQ-014 for explicitly stated core capabilities, cross-referenced to the earlier grouped requirements. The classification of other interactive analytics remains for review.
- 2026-11-03: Corrected the scope-tier mapping to distinguish REQ-003's original wording from the separately confirmed station-count scope in REQ-013; REQ-014 remains a separate Core requirement.
