# ConductSignal Artemis II Demo Summary

Script version: 0.4.1
Data phase: real_public_proxy_demo
Input findings: 4
Crew members: MMASH_001, MMASH_002, MMASH_003, MMASH_004
Proxy datasets listed: NHANES 2017-2018, PhysioNet MMASH, public Inspiration4/SOMA supplementary inventory

## Public Source Row Counts

- inspiration4_inventory_rows: 0
- mmash_observation_rows: 175
- nhanes_observation_rows: 56
- proxy_observations.csv: 231
- real_findings: 4
- reference_slices.csv: 23

## Public Sources

- NHANES 2017-2018: https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?BeginYear=2017
- PhysioNet MMASH: https://physionet.org/content/mmash/1.0.0/
- Inspiration4/SOMA public supplementary sources: https://www.nature.com/articles/s41586-024-07639-y

## Computed Phase 1 Tables

- baseline_table.csv: 92 rows
- within_subject_change_table.csv: 231 rows
- reference_anchor_table.csv: 92 rows
- change_point_table.csv: 11 rows
- recovery_table.csv: 92 rows
- concordance_table.csv: 4 rows

## Strongest Finding

- Finding: real_003
- Astronaut: MMASH_003
- Phase: transit
- Score: 0.888
- Claim: MMASH_003 showed its largest public MMASH-derived transit-window change in steps_per_minute, with cross-modal support.

## Crew Summary

| Astronaut | Findings | Strongest score | Max abs effect | Modalities | Change points | Missing values |
|---|---:|---:|---:|---|---:|---:|
| MMASH_001 | 1 | 0.602 | 0.655 | behavioral, standard_measures | 1 | 0 |
| MMASH_002 | 1 | 0.685 | 1.318 | behavioral, standard_measures | 1 | 0 |
| MMASH_003 | 1 | 0.888 | 2.944 | behavioral, standard_measures | 1 | 0 |
| MMASH_004 | 1 | 0.720 | 1.602 | behavioral, standard_measures | 1 | 0 |

## Guardrail

Derived public proxy data demonstrate method mechanics for Artemis II-style analysis. Controlled-access and private astronaut data remain outside this public packet.
