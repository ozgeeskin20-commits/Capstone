# Open Questions and Assumptions

These items are unresolved; none is an approved architectural decision or confirmed requirement.

| ID | Type | Question or assumption | Status |
| --- | --- | --- | --- |
| Q-001 | Question | Which application technologies and architecture should be proposed? | Open; no stack selected. |
| Q-002 | Question | What are the EPDK sources' access methods, fields, historical coverage and permitted uses? | Open; see [data sources](../DATA_SOURCES.md). |
| Q-003 | Question | What dated evidence and method can support historical monthly installation counts? | Open; a single snapshot is insufficient. |
| Q-004 | Question | What private vulnerability reporting channel will be configured? | Open; see [security policy](../../SECURITY.md). |
| Q-005 | Question | Which approved implementation tasks, if any, will be associated with GitHub Issues? | Open; see clarification below. No issue numbers recorded. |
| Q-006 | Question | How can the team provide the Colab notebook, representative output samples, dependencies, schema and retrieval metadata for review without exposing credentials or private Drive information? | Open; prototype not independently reviewed or integrated. |
| Q-007 | Question | What API quotas, rate limits, availability and schema-change behavior apply? | Open; existence and limits unverified. |
| Q-008 | Question | How should interactive analytics beyond the core dashboard and historical development analysis beyond station counts be classified? | Open; existing confirmed requirements are retained without assigning an unapproved tier. |

### Q-005 clarification — 2026-11-03

The original question above is preserved. The user has confirmed [REQ-012](REQUIREMENTS.md): all accepted architectural decisions must be recorded in GitHub Issues after the complete architecture decision set has been reviewed and approved by the user. Whether to use one issue per ADR or another grouping strategy remains open, as does the original question for other implementation tasks. Issue creation must also wait for user approval of the grouping strategy; the existing conditional instruction supplies authorization once both conditions are satisfied.

Record assumptions explicitly with their evidence and owner when they arise. Resolve questions by recording the outcome and relevant approval without deleting their history.
