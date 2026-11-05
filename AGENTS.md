# Project instructions for Codex

Follow the user's current instructions and preserve existing approved documents and uncommitted work.

## Project instruction hierarchy

1. Current explicit user instructions.
2. Previously user-approved requirements and accepted architecture decisions.
3. Project governance documents.
4. Assistant recommendations and unverified assumptions.

Recommendations and assumptions are not approved decisions. Never silently change confirmed requirements or erase history. If a current instruction materially conflicts with an earlier approved decision or requirement, stop the affected work, explain the conflict and implications, and seek clarification or explicit supersession; record approved changes and their history. Stop when material ambiguity prevents safe implementation.

## Before implementation

1. Read this file and [the project memory index](docs/project-memory/README.md).
2. Review relevant [requirements](docs/project-memory/REQUIREMENTS.md), open questions and architecture decision records (ADRs).
3. Check the current Git branch and working tree; identify the intended files and scope before making changes.
4. Do not make architectural changes without explicit user approval. Record proposed decisions using the ADR template; never mark an ADR Accepted without explicit user approval.
5. Treat assumptions as assumptions, not confirmed requirements. Preserve requirement history and identifiers.

## Conflicts and evidence

Distinguish user-confirmed requirements, accepted architecture decisions, assistant recommendations and unverified assumptions. Recommendations and assumptions are not approvals.

If a new instruction conflicts with an accepted ADR, a confirmed requirement or an approved project constraint, stop the affected implementation. Explain the exact conflict, identify the affected ADR and REQ IDs (or state when none applies), present alternatives and their consequences, and request explicit user approval before proceeding. Never silently override an accepted decision.

Only ADRs with status Accepted are eligible for the architecture-decision GitHub Issue workflow. Draft, Proposed and Rejected ADRs are excluded; never create an issue for an unapproved decision. The user's existing conditional instruction authorizes recording accepted decisions once the complete architecture decision set and the issue grouping strategy have both been reviewed and approved by the user. Do not create those issues before both conditions are satisfied or seek redundant approval for that already authorized action.

## After each task

Run appropriate tests or checks, report modified files and results, identify unresolved risks, and record a session summary in [SESSION_LOG.md](docs/project-memory/SESSION_LOG.md). State when a check was not run and why. Update relevant documentation when an approved decision or requirement changes. Do not invent results.

Do not put secrets, credentials or private correspondence in documentation. Do not automatically commit, push or create GitHub Issues without authorization. Obtain user approval before publishing changes to GitHub; existing explicit conditional authorization applies when its conditions are satisfied. Follow the two-branch workflow in [CONTRIBUTING.md](CONTRIBUTING.md).
