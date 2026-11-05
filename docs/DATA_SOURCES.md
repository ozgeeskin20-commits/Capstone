# Data Sources

## Planned EPDK sources

Three EPDK source categories are planned. None is integrated into the repository. Available fields, historical coverage, access conditions and permitted uses require investigation for each source; no assumption is made that all historical monthly data is available.

| Planned source | Expected analytical role | Reference and access status |
| --- | --- | --- |
| EPDK Şarj Hizmeti Piyasası İstatistikleri (charging service market statistics) | Market-level development and aggregate indicators. | Access method and reference URL have not been verified. |
| EPDK Şarj Ağı İşletmecisi (SAİ) Lisans Listesi (charging network operator license list) | Identification of licensed operators and licensing information. | Access method and reference URL have not been verified. |
| EPDK Şarj İstasyonları API (charging stations API) | Station-level infrastructure, location, socket and capacity analysis, subject to the fields actually available. | [API documentation reference](https://apigateway.epdk.gov.tr/sarjIstasyonlari?swagger) is verified; API access conditions and available fields still require investigation. |

The software license does not automatically grant rights to redistribute EPDK data.

For each source, investigate and record its identity, access method, available fields, retrieval timestamps, historical coverage, provenance, quality, and usage and redistribution rights. API quotas, rate limits, service availability and schema changes are investigation topics: their existence and actual limits are unverified.

## External proof of concept

The team reports that a teammate developed a Google Colab EPDK API data collection script whose outputs are saved to Google Drive. It exists outside this repository and is not an integrated pipeline or selected production architecture. The notebook has not been independently reviewed; endpoint, dependencies, schema, schedule, output completeness, validation and historical sufficiency are unverified. Obtain and review the notebook, samples and retrieval metadata without publishing credentials or private Drive information; see [Q-006](project-memory/OPEN_QUESTIONS.md).

## Provenance and snapshots

Future collection should record the source, retrieval time, relevant coverage, transformation steps and any limitations so results can be traced and reproduced. A snapshot represents the information available at retrieval time, subject to the source's own update schedule. Repeated, consistently documented snapshots or another suitable historical source may support comparisons, but changes between snapshots require careful interpretation.

## Freshness, history and quality

Source updates may lag real-world changes, and coverage or definitions may change. Missing, duplicate, inconsistent or corrected records can affect geographic, operator, socket and capacity measures. Validate fields, units, identifiers and completeness before drawing conclusions. A single snapshot cannot independently establish historical monthly installation counts; even differences between snapshots do not automatically establish installation dates. Historical installation counts require suitable dated evidence and a documented method.

Do not place credentials or sensitive access information in the repository.
