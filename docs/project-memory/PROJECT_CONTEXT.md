# Project Context

Capstone is a planned market intelligence and decision-support system for Türkiye's EV charging market. It aims to support reliable, reproducible and maintainable data collection, processing and analysis, including geographical, socket, capacity and operator comparisons and reports. See [project scope](../PROJECT_SCOPE.md) for details.

The five contributors listed in the [README](../../README.md) are Özge Eskin, İrem Genç, Nilay Dinçer, Furkan Alim and Mohammed Ali Chtibi. The project owner reports an original Siemens project request; the available records do not identify which individual features Siemens requested. Team proposals and the owner's 2026-11-03 scope classification must not be attributed to Siemens without evidence.

The owner's approved planning tiers give first priority to core EPDK-based collection, monthly and yearly station counts, capacity and power-class distribution, operator comparison by installed power, and an interactive dashboard. Extended scope covers geographic analysis, AC/DC comparison, connector types and standards, operator market share and professional reports. No specific future feature list is approved; see [scope](../PROJECT_SCOPE.md).

The intended EPDK source categories and limitations are described in [data sources](../DATA_SOURCES.md). No source integration or application capabilities have been implemented. Historical installation counts require suitable dated evidence. EVCify is a high-level benchmark only; see [product reference](../PRODUCT_REFERENCE.md).

The team reports an existing external Google Colab proof of concept that collects EPDK API data and saves outputs to Google Drive. It is not integrated in this repository, independently reviewed or selected as production architecture. Its dependencies, schema, collection details, quality and historical sufficiency remain unverified.

The approved initial documentation baseline is commit `5197b4656297eb0d0bf3715b1882d12e49482d03`. As verified on 2026-11-03, exactly two local branches exist: active development branch `develop` and stable branch `main`; both point to that initial documentation commit. Remote publication or synchronization is not implied.

No application stack or architecture has been selected. The project is source-available under [PolyForm Noncommercial 1.0.0](../../LICENSE); external data and materials have their own terms. See [open questions](OPEN_QUESTIONS.md) for unresolved matters.
