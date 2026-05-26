# ConductSignal Artemis II Demo

This directory contains the executable ConductSignal demonstration for the Artemis II public code/data repository.

The demo reads normalized public proxy tables from `artemis/data/`, uses the generated findings in `api/artemis_findings.json`, and creates public tables and figures under `artemis/output/`.

To regenerate the public proxy inputs first, run:

```powershell
python scripts\build_real_proxy_demo_data.py --max-mmash-subjects 4
```

## Quick Start

Run from the repository root:

```powershell
python artemis\run_demo.py
```

No third-party Python dependencies are required.

## Outputs

| File | Description |
|---|---|
| `artemis/output/baseline_table.csv` | Per-subject baseline center, spread, stability, and provenance. |
| `artemis/output/within_subject_change_table.csv` | Baseline-normalized deltas, robust z-scores, intervals, and data quality. |
| `artemis/output/reference_anchor_table.csv` | Reference datasets, filters, empirical percentiles, and mapping status. |
| `artemis/output/change_point_table.csv` | Standard-library two-window mean-shift change-point output. |
| `artemis/output/recovery_table.csv` | Peak effect, last observed effect, recovery status, and slope estimate. |
| `artemis/output/concordance_table.csv` | Same-subject, same-phase descriptive multimodal concordance. |
| `artemis/output/finding_atlas.csv` | Ranked finding evidence table. |
| `artemis/output/crew_state_summary.csv` | Per-astronaut summary table. |
| `artemis/output/missingness_report.csv` | Explicit missingness report. |
| `artemis/output/trace_long.csv` | Long-form time series export. |
| `artemis/output/method_provenance.json` | Input hashes, output hashes, source URLs, and algorithm settings. |
| `artemis/output/crew_state_summary.svg` | Crew-level visual summary. |
| `artemis/output/top_findings.svg` | Top finding prominence figure. |
| `artemis/output/submission_summary.md` | Human-readable run summary. |

## Interpretation

This demo shows method mechanics on public proxy data for Artemis II-style individual trajectory review. The generated tables use NHANES 2017-2018, PhysioNet MMASH, and public Inspiration4/SOMA supplementary-source inventory to exercise the challenge data types: Standard Measures, ARCHeR, and Immune Biomarkers. The pipeline demonstrates within-subject effect reporting, change-point evidence, cross-modal concordance, missingness exposure, and a ranked review queue.

ConductSignal interface:

https://conductsignal.com/artemis
