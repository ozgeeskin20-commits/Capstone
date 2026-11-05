# Project Scope

## Purpose and problem

The project aims to provide reliable, reproducible and maintainable market intelligence and decision support for Türkiye's EV charging infrastructure. Fragmented or time-dependent data makes geographic and operator comparisons difficult without clear methods and provenance.

## Intended users

Potential users include researchers, market analysts, charging infrastructure stakeholders and decision makers.

## Core features

The project owner approved this planning classification on 2026-11-03. Core features receive first implementation priority:

- EPDK-based EV charging market data collection.
- Monthly and yearly charging station count analysis.
- Installed charging capacity and power-class distribution.
- Charging network operator comparison by installed power.
- An interactive market intelligence dashboard.

## Extended features

These enrich the product and are not prerequisites for completing the initial core product:

- Analyze infrastructure by province and district.
- Analyze and compare AC/DC distribution, connector types and technical standards.
- Analyze operator market shares using documented definitions.
- Produce professional market intelligence reports.

## Future improvements

No specific future feature list has been approved. Ideas may be proposed separately and require explicit approval before becoming confirmed scope.

## Data limitations

A single current snapshot cannot establish historical monthly installation dates. Monthly new-installation analysis requires appropriate dated historical evidence or a validated collection methodology; snapshot differences are not confirmed installation dates. Source access, quality and rights remain subject to investigation; see [data sources](DATA_SOURCES.md).

## Out of scope

This initial documentation phase excludes application implementation, operational charging control, payment processing and redistribution of external datasets without assessment of applicable rights. Future scope is subject to review.

## Expected outputs and status

The intended outputs are analytical views, comparisons and reports with documented sources and limitations. These are planned, not implemented. No application stack or architecture has been selected.

The team reports a separate Google Colab API collection proof of concept that saves outputs to Google Drive. It is not integrated into this repository, independently reviewed or selected as production architecture; see [data sources](DATA_SOURCES.md).
