# Türkiye Electric Vehicle Charging Market Intelligence and Decision Support System

Capstone is a planned platform for reliable, reproducible and maintainable collection, processing and analysis of information about Türkiye's electric vehicle charging market. It aims to support market intelligence and informed decisions.

## Problem statement

Understanding charging infrastructure across locations, technologies and operators requires consistent data and transparent methods. Changes over time are especially difficult to interpret without comparable historical observations.

## Objectives and expected capabilities

- Analyze infrastructure by province and district, including AC/DC socket distribution, installed charging capacity, connectors and technical standards.
- Compare licensed charging network operators and analyze market shares using clearly defined measures.
- Examine infrastructure development and monthly new installations where suitable historical data exists.
- Provide interactive analytics, dashboards and professional market intelligence reports.

## Current status and planned work

The repository is being established from scratch. No application capabilities or API integrations have been implemented. All capabilities above are planned and depend on data availability and future design decisions.

## Technology stack and setup

The application technology stack has not been selected. Installation and setup instructions, technical details, and testing guidance will be added in later development phases.

## Repository structure

- [LICENSE](LICENSE): public license terms and required notice.
- [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [CHANGELOG.md](CHANGELOG.md): project practices.
- [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): ownership and third-party notices.
- [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md), [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md), and [docs/PRODUCT_REFERENCE.md](docs/PRODUCT_REFERENCE.md): scope, data and benchmark context.

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
