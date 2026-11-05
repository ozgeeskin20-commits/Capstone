# Contributing

Contributions should be accurate, reproducible, respectful of data and intellectual property rights, and limited to an agreed scope. Do not include credentials, private correspondence or sensitive information.

## Branches and workflow

The project maintains exactly two branches: `main` is the stable production and release branch, and `develop` is the active development and integration branch. As verified on 2026-11-03, the two local branches both point to the initial documentation commit `5197b46`. This local state does not establish remote publication or synchronization. Do not create any additional temporary or permanent branches; see [REQ-007](docs/project-memory/REQUIREMENTS.md).

Discuss substantive changes before implementation. Make development changes on `develop` and keep them focused. Review and approve a stable release on `develop`, then promote it from `develop` to `main` through a pull request.

## Quality, documentation and testing

Write maintainable, understandable code when implementation begins. Document behavior, assumptions, data provenance and limitations; update relevant documentation and third-party notices when changes require it. Add or update meaningful tests for changed behavior and run the checks applicable to the change. If a check cannot be run, explain why in the pull request. Specific tools and automation have not yet been selected.

## Review and commits

Pull requests should describe the problem, changes, validation performed and remaining limitations. A reviewer should inspect the change and resolve substantive feedback before integration. Use concise, imperative commit subjects that describe the change; add a body when context is needed. Do not include secrets in commits or pull requests.
