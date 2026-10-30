# Data Sources

## Planned EPDK sources

Three EPDK source categories are planned. None is integrated into the repository. Available fields, historical coverage, access conditions and permitted uses require investigation for each source; no assumption is made that all historical monthly data is available.

| Planned source | Expected analytical role | Reference and access status |
| --- | --- | --- |
| EPDK Şarj Hizmeti Piyasası İstatistikleri (charging service market statistics) | Market-level development and aggregate indicators. | Access method and reference URL have not been verified. |
| EPDK Şarj Ağı İşletmecisi (SAİ) Lisans Listesi (charging network operator license list) | Identification of licensed operators and licensing information. | Access method and reference URL have not been verified. |
| EPDK Şarj İstasyonları API (charging stations API) | Station-level infrastructure, location, socket and capacity analysis, subject to the fields actually available. | [API documentation reference](https://apigateway.epdk.gov.tr/sarjIstasyonlari?swagger) is verified; API access conditions and available fields still require investigation. |

The software license does not automatically grant rights to redistribute EPDK data.

## Provenance and snapshots

Future collection should record the source, retrieval time, relevant coverage, transformation steps and any limitations so results can be traced and reproduced. A snapshot represents the information available at retrieval time, subject to the source's own update schedule. Repeated, consistently documented snapshots or another suitable historical source may support comparisons, but changes between snapshots require careful interpretation.

## Freshness, history and quality

Source updates may lag real-world changes, and coverage or definitions may change. Missing, duplicate, inconsistent or corrected records can affect geographic, operator, socket and capacity measures. Validate fields, units, identifiers and completeness before drawing conclusions. A single snapshot cannot independently establish historical monthly installation counts; even differences between snapshots do not automatically establish installation dates. Historical installation counts require suitable dated evidence and a documented method.

Do not place credentials or sensitive access information in the repository.
