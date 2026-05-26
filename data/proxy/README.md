# Proxy Datasets for Artemis II Challenge

NASA-curated proxy datasets used to demonstrate the analytical methodology.

## Primary Demo Dataset Status

| Dataset | Source | Status | Maps to Study |
|---------|--------|--------|---------------|
| NHANES 2017-2018 | CDC | Open access; direct XPT downloads | Standard Measures baseline |
| PhysioNet MMASH | PhysioNet | Open access; direct ZIP download | ARCHeR behavioral/activity/sleep proxy |
| Inspiration4 | NASA OSDR | Selected processed tabular files open; raw/gated files excluded | Spaceflight-like validation for physiology and immune markers |
| UTMB Bedrest | NASA NLSP | Requires access request | All three studies |
| ImmPort | ImmPort.org | Requires registration | Immune Biomarkers |

Download the primary demo files with:

```bash
python scripts/download_primary_demo_data.py
```

Raw data is written to `data/raw/primary_demo/` and is intentionally ignored by
Git. The downloader writes `data/raw/primary_demo/download_manifest.json` with
file paths, byte counts, and SHA-256 hashes for local reproducibility.

## Primary Demo Source URLs

### NHANES

- `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.xpt`
- `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BMX_J.xpt`
- `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/CBC_J.xpt`
- `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BIOPRO_J.xpt`
- `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/SMQ_J.xpt`
- `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/PAQ_J.xpt`

### PhysioNet MMASH

- `https://physionet.org/files/mmash/1.0.0/MMASH.zip`

### NASA OSDR Inspiration4

The downloader reads file manifests from:

- `https://osdr.nasa.gov/osdr/data/osd/files/569`
- `https://osdr.nasa.gov/osdr/data/osd/files/575`
- `https://osdr.nasa.gov/osdr/data/osd/files/656`

Selected files:

- `OSD-569_metadata_OSD-569-ISA.zip`
- `LSDS-7_Complete_Blood_Count_CBC_TRANSFORMED.csv`
- `OSD-575_metadata_OSD-575-ISA.zip`
- `LSDS-8_Comprehensive_Metabolic_Panel_CMP_TRANSFORMED.csv`
- `LSDS-8_Multiplex_serum_immune_EvePanel_TRANSFORMED.csv`
- `LSDS-8_Multiplex_serum_cardiovascular_EvePanel_TRANSFORMED.csv`
- `LSDS-8_Multiplex_serum.immune.AlamarPanel_TRANSFORMED.csv`
- `OSD-656_metadata_OSD-656-ISA.zip`
- `LSDS-64_Multiplex_urine.immune.AlamarPanel_TRANSFORMED.csv`

## Astronaut-Like Cohort Filtering (NHANES)

NHANES filtered for healthy, active, educated, non-smoking adults aged 30-55
to match astronaut demographics (per NASA SME recommendation).

## Data Fallback Matrix

If primary datasets are unavailable:

| Module | Primary | Fallback 1 | Fallback 2 |
|--------|---------|------------|------------|
| Behavioral | PhysioNet actigraphy | NHANES accelerometry | Synthetic |
| Physiological | UTMB bedrest (NLSP) | NHANES labs + exam | Inspiration4 |
| Immune | ImmPort study | NHANES CBC + CRP | Inspiration4 immune |

## Data Not Committed to Git

Raw data files are in `.gitignore`. Download scripts are provided in each
subdirectory. Run them to reproduce the dataset locally.
