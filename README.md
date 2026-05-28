# ConductSignal Artemis II Public Demo

Public code, derived public-proxy data, provenance, and reproducible outputs for the ConductSignal Artemis II methodology demonstration.

Version: `0.2.5`

Public repository:

https://github.com/ConductScience-Foundation/artemis-ii-conductsignal-submission

Public review page:

https://conductsignal.com/artemis

## Repository Boundary

This Foundation repository contains only public, reproducible materials:

- Public demo code.
- Derived public-proxy data tables.
- Public provenance manifests.
- Generated public demo outputs.

It does not contain generated submission PDFs, upload bundles, private QA records, raw source-data caches, controlled-access astronaut data, or private clinical data.

## Plain-Language Method

The challenge asks for a method that can extract useful evidence from a very small astronaut cohort with many measurements. The ConductSignal public demo shows a reference-anchored N-of-1 atlas:

- Treat each astronaut-like proxy subject as their own longitudinal baseline.
- Measure what changed from that person's baseline.
- Add public reference context where it is defensible.
- Mark uncertainty, missingness, and recovery status.
- Promote findings that have strong effect size, change-point support, persistence, and cross-modal concordance.
- Keep interpretation at the individual trajectory and review-priority level for `n=4`.

## Public Data And Outputs

Tracked public inputs:

```text
artemis/data/proxy_observations.csv
artemis/data/reference_slices.csv
artemis/data/source_manifest.json
artemis/data/data_provenance.md
api/artemis_findings.json
```

Tracked public outputs:

```text
artemis/output/
```

Raw public source files are intentionally excluded from Git. The source-data builder downloads or reuses public NHANES and MMASH data and inventories public Inspiration4/SOMA supplementary files when present locally.

## Run The Demo

The core demo uses only the Python standard library. It reads the included derived public-proxy tables and generated findings.

```powershell
python artemis\run_demo.py
```

Expected outputs are written to:

```text
artemis/output/
```

## Rebuild Derived Public Proxy Inputs

The optional source-data rebuild uses public NHANES and MMASH inputs and requires the packages in `requirements.txt`.

```powershell
pip install -r requirements.txt
python scripts\build_real_proxy_demo_data.py --max-mmash-subjects 4
python artemis\run_demo.py
```

## QA Status

Current public repository checks:

- `python -m pytest`: public boundary and raw-data checks.
- `detect-secrets scan`: public repository secret scan.
- `bandit -r . --severity-level medium`: medium/high security scan.
- `pip-audit -r requirements.txt`: dependency vulnerability scan.
