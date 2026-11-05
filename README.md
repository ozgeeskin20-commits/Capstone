# Türkiye Electric Vehicle Charging Market Intelligence and Decision Support System

Capstone is a planned platform for reliable, reproducible and maintainable collection, processing and analysis of information about Türkiye's electric vehicle charging market. It aims to support market intelligence and informed decisions.

## Problem statement

Understanding charging infrastructure across locations, technologies and operators requires consistent data and transparent methods. Changes over time are especially difficult to interpret without comparable historical observations.

## Objectives and expected capabilities

The project owner approved the following planning tiers on 2026-11-03. Core features have first implementation priority; extended features are not prerequisites for the initial core product.

**Core:** EPDK-based data collection; monthly and yearly charging station counts; installed capacity and power-class distribution; operator comparison by installed power; and an interactive market intelligence dashboard.

**Extended:**

- Analyze infrastructure by province and district, AC/DC distribution, connectors and technical standards.
- Analyze operator market shares using clearly defined measures.
- Produce professional market intelligence reports.

No specific future feature list is approved. See the [scope](docs/PROJECT_SCOPE.md).

## Current status and planned work

The repository contains an initial documentation and governance baseline. Application development has not started in this repository, and no repository-integrated EPDK pipeline exists. All capabilities above are planned and depend on data availability and future design decisions.

The team reports an existing external Google Colab proof of concept that collects EPDK API data and saves outputs to Google Drive. It is not integrated into this repository or independently reviewed, and is not a selected production architecture. Its implementation, quality and historical coverage remain unverified.

## Technology stack and setup

The application technology stack has not been selected. Installation and setup instructions, technical details, and testing guidance will be added in later development phases.

## Repository structure

- [LICENSE](LICENSE): public license terms and required notice.
- [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [CHANGELOG.md](CHANGELOG.md): project practices.
- [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): ownership and third-party notices.
- [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md), [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md), and [docs/PRODUCT_REFERENCE.md](docs/PRODUCT_REFERENCE.md): scope, data and benchmark context.
- [Project memory index](docs/project-memory/README.md): requirements, open questions, session history, risks and issue governance.
- [Architecture overview](docs/architecture/ARCHITECTURE_OVERVIEW.md) and [ADR template](docs/architecture/decisions/ADR-000-TEMPLATE.md): decision process; no architecture has been selected.

## Data sources and limitations

The planned EPDK sources are charging service market statistics, the charging network operator (SAİ) license list, and the [charging stations API](https://apigateway.epdk.gov.tr/sarjIstasyonlari?swagger). None is integrated. Access methods, coverage, freshness, quality and usage rights must be assessed. A single snapshot cannot independently establish historical monthly installation counts. See [data sources](docs/DATA_SOURCES.md).

## License

This is source-available software under the [PolyForm Noncommercial License 1.0.0](LICENSE). Commercial usage is not granted by the public license; separate written permission may be granted by the relevant copyright holders. External data and materials are subject to their own rights and terms.

## Contributors

- Özge Eskin
- İrem Genç
- Nilay Dinçer
- Furkan Alim
- Mohammed Ali Chtibi
