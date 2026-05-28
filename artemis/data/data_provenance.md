# Data Provenance

**Title:** Public Proxy Data Provenance for the Artemis II N-of-1 Multimodal Change Atlas

## Summary

This document records the public sources, transforms, and access boundaries used to regenerate the normalized proxy tables for the Artemis II public demo. This repository contains derived public proxy data, with controlled-access and private astronaut data kept outside the repository.

## Source Summary

| Source | Role | Access | URL |
|---|---|---|---|
| NHANES 2017-2018 | Standard Measures reference context and example physiological rows | public | https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?BeginYear=2017 |
| PhysioNet MMASH | ARCHeR-like wearable, sleep, activity, and salivary time-series proxy | public open access | https://physionet.org/content/mmash/1.0.0/ |
| Inspiration4/SOMA public supplementary sources | Human spaceflight biology source inventory and access-boundary context | public supplementary inventory; controlled-access individual clinical values kept outside this repository | https://www.nature.com/articles/s41586-024-07639-y |

## Reproduction Commands

```powershell
python scripts\build_real_proxy_demo_data.py --max-mmash-subjects 4
python artemis\run_demo.py
```

## Row Counts

| Output | Rows |
|---|---:|
| proxy_observations.csv | 231 |
| reference_slices.csv | 23 |
| nhanes_observation_rows | 56 |
| mmash_observation_rows | 175 |
| real_findings | 4 |
| inspiration4_inventory_rows | 0 |

## Variable Mapping

| Artemis study area | Public source | Variables generated |
|---|---|---|
| Standard Measures | NHANES, MMASH | BMI, blood pressure, CBC/chemistry references, heart rate, cortisol_norm |
| ARCHeR | MMASH | steps_per_minute, vector_magnitude, lying_ratio, sleep_efficiency, WASO, sleep_minutes, melatonin_norm |
| Immune Biomarkers | NHANES, Inspiration4/SOMA inventory | WBC and platelet reference context; public Inspiration4/SOMA source inventory and access-boundary mapping |

## Inclusion And Exclusion Rules

- NHANES reference rows use adults age 30-55, non-smokers where available, and recreationally active participants where available.
- MMASH rows use the first four complete public subject folders by numeric subject ID.
- MMASH pseudo-phases split each 24-hour record into baseline, daytime/transit-mechanics, and recovery blocks. These analysis windows are distinct from mission phases.
- Inspiration4/SOMA inventory rows use public supplementary materials, with controlled-access individual clinical values kept outside this repository.

## Missingness Handling

The builder includes available source values in numeric derived tables and records missingness explicitly in downstream demo outputs. Variables are filtered per variable, preserving usable modality-specific evidence.

## Output Hashes

| File | SHA-256 |
|---|---|
| `artemis/data/proxy_observations.csv` | `021431821916fa747d162049908742af1bf218537b1ed5e28fb3ca09ab7c616f` |
| `artemis/data/reference_slices.csv` | `0b9c3a536839b558bf10f2afc0621319a5c146edb1b40fe64ddc4fa6a36c8e86` |
| `api/artemis_findings.json` | `92d86e65a623dc56e714a811885b6f703ac20a4a5708d6a40a40fe2de39462bf` |

## Interpretation Boundary

The generated outputs show that the method can transform public proxy datasets into transparent individual-level evidence products for Artemis II-style review. Interpretation is bounded to method demonstration, individual trajectory review, and reproducible evidence generation.
