# GitHub Issue Register

Use this register to connect approved implementation tasks to actual GitHub Issues. Record only verified issue numbers and links, the approved task, related requirements or ADRs, and current status. Do not infer approval from an issue or invent an issue number. Creating an issue requires user authorization, including any applicable existing conditional authorization.

## Architecture decision workflow

Under [REQ-012](../project-memory/REQUIREMENTS.md), all accepted architectural decisions must eventually be represented in GitHub Issues. Only ADRs with status Accepted are eligible for this workflow; Draft, Proposed and Rejected ADRs are excluded. Never create an issue for an unapproved decision. Do not create issues until the complete architecture decision set has been reviewed and approved by the user and the issue grouping strategy has also been approved. The grouping strategy, including whether there should be one issue per ADR, remains unresolved in [Q-005](../project-memory/OPEN_QUESTIONS.md). The user's existing conditional instruction authorizes this workflow once those conditions are met; no redundant approval is required for the already authorized action.

When authorized, use the locally authenticated GitHub CLI and check for duplicate issues before creation. Include relevant ADR and REQ references, context, decision, rationale, risks and acceptance criteria. Record only actual, verified issue numbers and URLs; never invent them.

No approved implementation task has been linked to a verified GitHub Issue in this register.

| Approved task | GitHub Issue | Related requirements / ADRs | Status |
| --- | --- | --- | --- |
