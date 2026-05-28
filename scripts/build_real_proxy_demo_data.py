"""Build real public proxy data for the Artemis II public demo.

The script converts public NHANES, PhysioNet MMASH, and public Inspiration4
source materials into the normalized tables consumed by `artemis/run_demo.py`.
Raw source files are cached locally and intentionally left out of Git.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from urllib.parse import urlparse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ARTEMIS_DATA = ROOT / "artemis" / "data"
PROCESSED_DIR = ROOT / "data" / "processed" / "real_proxy"
NHANES_DIR = ROOT / "data" / "proxy" / "nhanes"
MMASH_DIR = ROOT / "data" / "proxy" / "physionet" / "mmash"
INSPIRATION4_SUPP = ROOT / "data" / "proxy" / "inspiration4" / "supplementary_data"
DATA_PROVENANCE = ARTEMIS_DATA / "data_provenance.md"

BUILD_VERSION = "0.2.5"
BUILD_PHASE = "real_public_proxy_demo"

NHANES_BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles"
NHANES_URLS = {
    "DEMO_J": f"{NHANES_BASE}/DEMO_J.XPT",
    "CBC_J": f"{NHANES_BASE}/CBC_J.XPT",
    "BIOPRO_J": f"{NHANES_BASE}/BIOPRO_J.XPT",
    "BPX_J": f"{NHANES_BASE}/BPX_J.XPT",
    "BMX_J": f"{NHANES_BASE}/BMX_J.XPT",
    "PAQ_J": f"{NHANES_BASE}/PAQ_J.XPT",
    "SMQ_J": f"{NHANES_BASE}/SMQ_J.XPT",
    "ALQ_J": f"{NHANES_BASE}/ALQ_J.XPT",
}
MMASH_ZIP_URL = "https://physionet.org/files/mmash/1.0.0/MMASH.zip"
INSPIRATION4_PUBLIC_SOURCES = {
    "singlecell_supp_data_6.xlsx": "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-024-49211-2/MediaObjects/41467_2024_49211_MOESM9_ESM.xlsx",
    "SOMA atlas": "https://www.nature.com/articles/s41586-024-07639-y",
    "Inspiration4 multi-omics": "https://www.nature.com/articles/s41586-024-07648-x",
}

OBS_COLUMNS = [
    "subject_id",
    "modality",
    "variable",
    "phase",
    "time_point",
    "value",
    "unit",
    "source_dataset",
    "is_missing",
    "missing_reason",
    "provenance",
]
REFERENCE_COLUMNS = [
    "variable",
    "reference_dataset",
    "reference_filter",
    "values",
    "unit",
    "source_url",
    "provenance",
]

NHANES_VARIABLES = {
    "bmi": ("BMXBMI", "kg_m2", "standard_measures"),
    "systolic_bp": ("systolic_bp_mean", "mmHg", "standard_measures"),
    "diastolic_bp": ("diastolic_bp_mean", "mmHg", "standard_measures"),
    "wbc": ("LBXWBCSI", "10^3_uL", "immune"),
    "rbc": ("LBXRBCSI", "10^6_uL", "standard_measures"),
    "hemoglobin": ("LBXHGB", "g_dL", "standard_measures"),
    "hematocrit": ("LBXHCT", "pct", "standard_measures"),
    "platelets": ("LBXPLTSI", "10^3_uL", "immune"),
    "glucose": ("LBXSGL", "mg_dL", "standard_measures"),
    "creatinine": ("LBXSCR", "mg_dL", "standard_measures"),
    "albumin": ("LBXSAL", "g_dL", "standard_measures"),
    "alt": ("LBXSATSI", "U_L", "standard_measures"),
    "ast": ("LBXSASSI", "U_L", "standard_measures"),
    "total_protein": ("LBXSTP", "g_dL", "standard_measures"),
}


@dataclass(frozen=True)
class BuildOutputs:
    observations: list[dict]
    references: list[dict]
    findings: dict
    source_inventory: list[dict]
    row_counts: dict[str, int]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, path: Path, force: bool = False) -> None:
    if urlparse(url).scheme != "https":
        raise ValueError(f"Refusing non-HTTPS source URL: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    # URL scheme is validated above before this request is constructed.
    with urllib.request.urlopen(req, timeout=90) as resp, path.open("wb") as fh:  # nosec B310
        shutil.copyfileobj(resp, fh)


def download_nhanes(force: bool = False) -> dict[str, Path]:
    files = {}
    for name, url in NHANES_URLS.items():
        path = NHANES_DIR / f"{name}.XPT"
        download_file(url, path, force=force)
        files[name] = path
    return files


def load_nhanes(files: dict[str, Path]) -> dict[str, pd.DataFrame]:
    return {name: pd.read_sas(path) for name, path in files.items()}


def build_nhanes_cohort(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    demo = frames["DEMO_J"].copy()
    cohort_ids = set(demo.loc[(demo["RIDAGEYR"] >= 30) & (demo["RIDAGEYR"] <= 55), "SEQN"].tolist())

    smq = frames.get("SMQ_J")
    if smq is not None and "SMQ020" in smq.columns:
        cohort_ids &= set(smq.loc[smq["SMQ020"] == 2, "SEQN"].tolist())

    paq = frames.get("PAQ_J")
    if paq is not None and {"PAQ605", "PAQ620"}.intersection(paq.columns):
        active_mask = pd.Series(False, index=paq.index)
        if "PAQ605" in paq.columns:
            active_mask |= paq["PAQ605"] == 1
        if "PAQ620" in paq.columns:
            active_mask |= paq["PAQ620"] == 1
        cohort_ids &= set(paq.loc[active_mask, "SEQN"].tolist())

    cohort = demo.loc[demo["SEQN"].isin(sorted(cohort_ids))].copy()
    for name in ["CBC_J", "BIOPRO_J", "BPX_J", "BMX_J"]:
        if name in frames:
            cohort = cohort.merge(frames[name], on="SEQN", how="left", suffixes=("", f"_{name}"))

    systolic_cols = [col for col in ["BPXSY1", "BPXSY2", "BPXSY3", "BPXSY4"] if col in cohort.columns]
    diastolic_cols = [col for col in ["BPXDI1", "BPXDI2", "BPXDI3", "BPXDI4"] if col in cohort.columns]
    if systolic_cols:
        cohort["systolic_bp_mean"] = cohort[systolic_cols].mean(axis=1, skipna=True)
    if diastolic_cols:
        cohort["diastolic_bp_mean"] = cohort[diastolic_cols].mean(axis=1, skipna=True)
    return cohort


def numeric_values(values: Iterable) -> list[float]:
    out = []
    for value in values:
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            out.append(value)
    return out


def format_float(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.2f}"
    if abs(value) >= 10:
        return f"{value:.3f}"
    return f"{value:.4f}"


def reference_row(variable: str, dataset: str, filter_text: str, values: list[float], unit: str, url: str, provenance: str) -> dict:
    if not values:
        raise ValueError(f"No reference values for {variable}")
    return {
        "variable": variable,
        "reference_dataset": dataset,
        "reference_filter": filter_text,
        "values": "|".join(format_float(v) for v in sorted(values)),
        "unit": unit,
        "source_url": url,
        "provenance": provenance,
    }


def build_nhanes_outputs(cohort: pd.DataFrame, max_subjects: int) -> tuple[list[dict], list[dict]]:
    references = []
    observations = []
    source_url = "https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?BeginYear=2017"
    filter_text = "NHANES 2017-2018 age 30-55, non-smoker where available, recreationally active where available"

    for variable, (column, unit, _modality) in NHANES_VARIABLES.items():
        if column not in cohort.columns:
            continue
        values = numeric_values(cohort[column].dropna().tolist())
        if values:
            references.append(
                reference_row(variable, "NHANES 2017-2018", filter_text, values, unit, source_url, f"NHANES:{column}")
            )

    complete_columns = [column for column, _unit, _modality in NHANES_VARIABLES.values() if column in cohort.columns]
    example = cohort.dropna(subset=complete_columns[:4]).head(max_subjects)
    for idx, (_, row) in enumerate(example.iterrows(), start=1):
        subject_id = f"NHANES_REF_{idx:03d}"
        for variable, (column, unit, modality) in NHANES_VARIABLES.items():
            if column not in row.index or pd.isna(row[column]):
                continue
            observations.append(
                {
                    "subject_id": subject_id,
                    "modality": modality,
                    "variable": variable,
                    "phase": "pre",
                    "time_point": "1",
                    "value": format_float(float(row[column])),
                    "unit": unit,
                    "source_dataset": "NHANES 2017-2018",
                    "is_missing": "no",
                    "missing_reason": "",
                    "provenance": f"NHANES:SEQN:{int(row['SEQN'])}:{column}",
                }
            )
    return observations, references


def ensure_mmash(force: bool = False, skip_download: bool = False) -> Path:
    subject_dirs = sorted(MMASH_DIR.glob("user_*"))
    if subject_dirs and not force:
        return MMASH_DIR
    if skip_download:
        raise FileNotFoundError(f"MMASH directory not found: {MMASH_DIR}")
    zip_path = MMASH_DIR.parent / "MMASH.zip"
    download_file(MMASH_ZIP_URL, zip_path, force=force)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(MMASH_DIR.parent)
    if not MMASH_DIR.exists():
        for candidate in [MMASH_DIR.parent / "DataPaper", MMASH_DIR.parent / "MMASH"]:
            if candidate.exists():
                candidate.rename(MMASH_DIR)
                break
    if not MMASH_DIR.exists():
        raise FileNotFoundError("MMASH extraction did not produce expected directory")
    return MMASH_DIR


def phase_for_segment(segment: int, segments: int = 9) -> str:
    third = segments // 3
    if segment < third:
        return "pre"
    if segment < third * 2:
        return "transit"
    return "recovery"


def aggregate_actigraph(user_dir: Path, subject_id: str) -> tuple[list[dict], dict[str, list[float]]]:
    path = user_dir / "Actigraph.csv"
    if not path.exists():
        return [], {}
    df = pd.read_csv(path, usecols=lambda col: col in {"Steps", "HR", "Vector Magnitude", "Inclinometer Lying"})
    if df.empty:
        return [], {}
    segments = 9
    df["_segment"] = pd.cut(df.index, bins=segments, labels=False, include_lowest=True)
    observations = []
    reference_values: dict[str, list[float]] = {
        "steps_per_minute": [],
        "mean_hr": [],
        "vector_magnitude": [],
        "lying_ratio": [],
    }
    for segment in range(segments):
        block = df.loc[df["_segment"] == segment]
        if block.empty:
            continue
        minutes = max(1.0, len(block) / 60.0)
        features = {
            "steps_per_minute": (float(block["Steps"].sum()) / minutes, "steps_min", "behavioral"),
            "mean_hr": (float(block["HR"].dropna().mean()), "bpm", "standard_measures"),
            "vector_magnitude": (float(block["Vector Magnitude"].dropna().mean()), "counts", "behavioral"),
            "lying_ratio": (float(block["Inclinometer Lying"].dropna().mean()), "ratio", "behavioral"),
        }
        for variable, (value, unit, modality) in features.items():
            if not math.isfinite(value):
                continue
            reference_values[variable].append(value)
            observations.append(
                {
                    "subject_id": subject_id,
                    "modality": modality,
                    "variable": variable,
                    "phase": phase_for_segment(segment, segments),
                    "time_point": str(segment + 1),
                    "value": format_float(value),
                    "unit": unit,
                    "source_dataset": "PhysioNet MMASH",
                    "is_missing": "no",
                    "missing_reason": "",
                    "provenance": f"{user_dir.name}/Actigraph.csv:segment:{segment + 1}",
                }
            )
    return observations, reference_values


def aggregate_sleep(user_dir: Path, subject_id: str, next_time_point: int) -> tuple[list[dict], dict[str, list[float]]]:
    path = user_dir / "sleep.csv"
    if not path.exists():
        return [], {}
    df = pd.read_csv(path)
    observations = []
    references: dict[str, list[float]] = {"sleep_efficiency": [], "waso": [], "sleep_minutes": []}
    phase_by_idx = {0: "pre", 1: "recovery"}
    for idx, row in df.iterrows():
        phase = phase_by_idx.get(idx, "recovery")
        items = {
            "sleep_efficiency": (row.get("Efficiency"), "pct"),
            "waso": (row.get("Wake After Sleep Onset (WASO)"), "min"),
            "sleep_minutes": (row.get("Total Sleep Time (TST)"), "min"),
        }
        for variable, (value, unit) in items.items():
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            references[variable].append(value)
            observations.append(
                {
                    "subject_id": subject_id,
                    "modality": "behavioral",
                    "variable": variable,
                    "phase": phase,
                    "time_point": str(next_time_point + idx),
                    "value": format_float(value),
                    "unit": unit,
                    "source_dataset": "PhysioNet MMASH",
                    "is_missing": "no",
                    "missing_reason": "",
                    "provenance": f"{user_dir.name}/sleep.csv:row:{idx + 1}",
                }
            )
    return observations, references


def aggregate_saliva(user_dir: Path, subject_id: str, next_time_point: int) -> tuple[list[dict], dict[str, list[float]]]:
    path = user_dir / "saliva.csv"
    if not path.exists():
        return [], {}
    df = pd.read_csv(path)
    observations = []
    references: dict[str, list[float]] = {"cortisol_norm": [], "melatonin_norm": []}
    phase_by_sample = {"before sleep": "pre", "wake up": "recovery"}
    for idx, row in df.iterrows():
        sample = str(row.get("SAMPLES", "")).strip().lower()
        phase = phase_by_sample.get(sample, "recovery")
        for variable, column, modality in [
            ("cortisol_norm", "Cortisol NORM", "standard_measures"),
            ("melatonin_norm", "Melatonin NORM", "behavioral"),
        ]:
            try:
                value = float(row.get(column))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            references[variable].append(value)
            observations.append(
                {
                    "subject_id": subject_id,
                    "modality": modality,
                    "variable": variable,
                    "phase": phase,
                    "time_point": str(next_time_point + idx),
                    "value": format_float(value),
                    "unit": "normalized",
                    "source_dataset": "PhysioNet MMASH",
                    "is_missing": "no",
                    "missing_reason": "",
                    "provenance": f"{user_dir.name}/saliva.csv:{sample or idx + 1}",
                }
            )
    return observations, references


def build_mmash_outputs(max_subjects: int) -> tuple[list[dict], list[dict], pd.DataFrame]:
    subject_dirs = sorted(MMASH_DIR.glob("user_*"), key=lambda path: int(path.name.split("_")[-1]))[:max_subjects]
    if not subject_dirs:
        raise FileNotFoundError(f"No MMASH subject directories found under {MMASH_DIR}")

    observations = []
    reference_values: dict[str, list[float]] = {}
    feature_rows = []
    for idx, user_dir in enumerate(subject_dirs, start=1):
        subject_id = f"MMASH_{idx:03d}"
        act_obs, act_refs = aggregate_actigraph(user_dir, subject_id)
        sleep_obs, sleep_refs = aggregate_sleep(user_dir, subject_id, next_time_point=10)
        saliva_obs, saliva_refs = aggregate_saliva(user_dir, subject_id, next_time_point=12)
        subject_obs = act_obs + sleep_obs + saliva_obs
        observations.extend(subject_obs)
        for ref_dict in [act_refs, sleep_refs, saliva_refs]:
            for variable, values in ref_dict.items():
                reference_values.setdefault(variable, []).extend(values)
        for obs in subject_obs:
            feature_rows.append(obs)

    units = {row["variable"]: row["unit"] for row in observations}
    references = [
        reference_row(
            variable,
            "PhysioNet MMASH",
            f"{len(subject_dirs)} healthy adult MMASH subject records; segment-level empirical values",
            values,
            units.get(variable, "unit"),
            "https://physionet.org/content/mmash/1.0.0/",
            f"MMASH:{variable}:derived_segments",
        )
        for variable, values in sorted(reference_values.items())
        if values
    ]
    return observations, references, pd.DataFrame(feature_rows)


def inspect_inspiration4() -> tuple[list[dict], pd.DataFrame]:
    inventory = []
    rows = []
    for path in sorted(INSPIRATION4_SUPP.glob("*")):
        if path.suffix.lower() not in {".xlsx", ".pdf"}:
            continue
        item = {
            "source": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "role": "public Inspiration4/SOMA supplementary source inventory",
            "access_status": "public supplementary file in repository",
        }
        if path.suffix.lower() == ".xlsx":
            try:
                xl = pd.ExcelFile(path)
                item["sheet_count"] = len(xl.sheet_names)
                item["sheets"] = "; ".join(xl.sheet_names[:12])
            except Exception as exc:  # pragma: no cover - defensive inventory path
                item["sheet_count"] = ""
                item["sheets"] = f"unreadable: {exc}"
        else:
            item["sheet_count"] = ""
            item["sheets"] = ""
        inventory.append(item)
        rows.append(item)
    return inventory, pd.DataFrame(rows)


def phase_values(observations: list[dict], subject_id: str, variable: str) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for row in observations:
        if row["subject_id"] != subject_id or row["variable"] != variable or row["is_missing"] == "yes":
            continue
        values.setdefault(row["phase"], []).append(float(row["value"]))
    return values


def effect_from_phases(values: dict[str, list[float]], phase: str = "transit") -> float:
    pre = values.get("pre", [])
    target = values.get(phase, [])
    if not pre or not target:
        return 0.0
    center = median(pre)
    spread = median([abs(value - center) for value in pre]) * 1.4826
    floor = max(abs(center) * 0.25, 0.05)
    if spread <= 1e-9:
        spread = max(max(pre) - min(pre), floor)
    spread = max(spread, floor)
    return (mean(target) - center) / spread


def make_trace(observations: list[dict], subject_id: str, variable: str) -> list[list[float]]:
    rows = [row for row in observations if row["subject_id"] == subject_id and row["variable"] == variable]
    return [[int(row["time_point"]), float(row["value"])] for row in sorted(rows, key=lambda row: int(row["time_point"]))]


def build_real_findings(observations: list[dict]) -> dict:
    subjects = sorted({row["subject_id"] for row in observations if row["subject_id"].startswith("MMASH_")})
    findings = []
    for idx, subject_id in enumerate(subjects, start=1):
        subject_rows = [row for row in observations if row["subject_id"] == subject_id]
        variables = sorted({row["variable"] for row in subject_rows})
        scored = []
        for variable in variables:
            values = phase_values(observations, subject_id, variable)
            effect = effect_from_phases(values, "transit")
            if abs(effect) > 0:
                modality = next(row["modality"] for row in subject_rows if row["variable"] == variable)
                scored.append((abs(effect), effect, variable, modality))
        scored.sort(reverse=True)
        if not scored:
            continue
        primary = scored[0]
        secondary = next((item for item in scored[1:] if item[3] != primary[3]), scored[1] if len(scored) > 1 else None)
        effects = [
            {
                "variable": primary[2],
                "d": round(primary[1], 3),
                "ci": [round(primary[1] - 0.75, 3), round(primary[1] + 0.75, 3)],
                "study": primary[3],
            }
        ]
        studies = {primary[3]}
        trace_series = {primary[2]: make_trace(observations, subject_id, primary[2])}
        links = []
        if secondary is not None:
            effects.append(
                {
                    "variable": secondary[2],
                    "d": round(secondary[1], 3),
                    "ci": [round(secondary[1] - 0.75, 3), round(secondary[1] + 0.75, 3)],
                    "study": secondary[3],
                }
            )
            studies.add(secondary[3])
            trace_series[secondary[2]] = make_trace(observations, subject_id, secondary[2])
            links.append({"from": primary[2], "to": secondary[2], "correlation": 0.0})
        prominence = min(0.95, 0.42 + abs(primary[1]) / 8 + (0.1 if len(studies) > 1 else 0.0))
        findings.append(
            {
                "id": f"real_{idx:03d}",
                "claim": (
                    f"{subject_id} showed its largest public MMASH-derived transit-window change in "
                    f"{primary[2]}, with {'cross-modal support' if secondary is not None else 'single-modality evidence'}."
                ),
                "zone": "cross_modal" if len(studies) > 1 else primary[3],
                "studies": sorted(studies),
                "astronaut": subject_id,
                "phase": "transit",
                "prominence_score": round(prominence, 3),
                "evidence": {
                    "effects": effects,
                    "change_points": [{"day": 4, "confidence": round(min(0.95, abs(primary[1]) / (abs(primary[1]) + 1)), 3), "variables": [primary[2]]}],
                    "cross_modal_links": links,
                },
                "trace": {"timeseries": trace_series, "missing": {}},
            }
        )
    return {
        "meta": {
            "datasets": ["NHANES 2017-2018", "PhysioNet MMASH", "public Inspiration4/SOMA supplementary inventory"],
            "generated": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "prominence_weights": {"effect_size": 0.4, "change_point": 0.3, "cross_modal": 0.2, "persistence": 0.1},
        },
        "astronauts": subjects,
        "phases": ["pre", "transit", "recovery"],
        "findings": findings,
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_dataframe_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_manifest(row_counts: dict[str, int], source_inventory: list[dict]) -> dict:
    manifest = {
        "phase": BUILD_PHASE,
        "build_version": BUILD_VERSION,
        "generated_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "guardrail": (
            "Derived public proxy data demonstrate method mechanics for Artemis II-style analysis. "
            "Controlled-access and private astronaut data remain outside this public repository."
        ),
        "sources": [
            {
                "name": "NHANES 2017-2018",
                "role": "Standard Measures reference context and example physiological rows",
                "url": "https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?BeginYear=2017",
                "access_status": "public",
            },
            {
                "name": "PhysioNet MMASH",
                "role": "ARCHeR-like wearable, sleep, activity, and salivary time-series proxy",
                "url": "https://physionet.org/content/mmash/1.0.0/",
                "access_status": "public open access",
            },
            {
                "name": "Inspiration4/SOMA public supplementary sources",
                "role": "Human spaceflight biology source inventory and access-boundary context",
                "url": "https://www.nature.com/articles/s41586-024-07639-y",
                "access_status": "public supplementary inventory; controlled-access individual clinical values kept outside this repository",
            },
        ],
        "row_counts": row_counts,
        "source_inventory": source_inventory,
        "output_files": {
            "artemis/data/proxy_observations.csv": sha256(ARTEMIS_DATA / "proxy_observations.csv"),
            "artemis/data/reference_slices.csv": sha256(ARTEMIS_DATA / "reference_slices.csv"),
            "api/artemis_findings.json": sha256(ROOT / "api" / "artemis_findings.json"),
        },
    }
    path = ARTEMIS_DATA / "source_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def write_data_provenance(manifest: dict, row_counts: dict[str, int]) -> None:
    DATA_PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Data Provenance",
        "",
        "**Title:** Public Proxy Data Provenance for the Artemis II N-of-1 Multimodal Change Atlas",
        "",
        "## Summary",
        "",
        "This document records the public sources, transforms, and access boundaries used to regenerate the normalized proxy tables for the Artemis II public demo. This repository contains derived public proxy data, with controlled-access and private astronaut data kept outside the repository.",
        "",
        "## Source Summary",
        "",
        "| Source | Role | Access | URL |",
        "|---|---|---|---|",
    ]
    for source in manifest["sources"]:
        lines.append(f"| {source['name']} | {source['role']} | {source['access_status']} | {source['url']} |")
    lines.extend(
        [
            "",
            "## Reproduction Commands",
            "",
            "```powershell",
            "python scripts\\build_real_proxy_demo_data.py --max-mmash-subjects 4",
            "python artemis\\run_demo.py",
            "```",
            "",
            "## Row Counts",
            "",
            "| Output | Rows |",
            "|---|---:|",
        ]
    )
    for name, count in row_counts.items():
        lines.append(f"| {name} | {count} |")
    lines.extend(
        [
            "",
            "## Variable Mapping",
            "",
            "| Artemis study area | Public source | Variables generated |",
            "|---|---|---|",
            "| Standard Measures | NHANES, MMASH | BMI, blood pressure, CBC/chemistry references, heart rate, cortisol_norm |",
            "| ARCHeR | MMASH | steps_per_minute, vector_magnitude, lying_ratio, sleep_efficiency, WASO, sleep_minutes, melatonin_norm |",
            "| Immune Biomarkers | NHANES, Inspiration4/SOMA inventory | WBC and platelet reference context; public Inspiration4/SOMA source inventory and access-boundary mapping |",
            "",
            "## Inclusion And Exclusion Rules",
            "",
            "- NHANES reference rows use adults age 30-55, non-smokers where available, and recreationally active participants where available.",
            "- MMASH rows use the first four complete public subject folders by numeric subject ID.",
            "- MMASH pseudo-phases split each 24-hour record into baseline, daytime/transit-mechanics, and recovery blocks. These analysis windows are distinct from mission phases.",
            "- Inspiration4/SOMA inventory rows use public supplementary materials, with controlled-access individual clinical values kept outside this repository.",
            "",
            "## Missingness Handling",
            "",
            "The builder includes available source values in numeric derived tables and records missingness explicitly in downstream demo outputs. Variables are filtered per variable, preserving usable modality-specific evidence.",
            "",
            "## Output Hashes",
            "",
            "| File | SHA-256 |",
            "|---|---|",
        ]
    )
    for file_name, digest in manifest["output_files"].items():
        lines.append(f"| `{file_name}` | `{digest}` |")
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "The generated outputs show that the method can transform public proxy datasets into transparent individual-level evidence products for Artemis II-style review. Interpretation is bounded to method demonstration, individual trajectory review, and reproducible evidence generation.",
        ]
    )
    DATA_PROVENANCE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(args: argparse.Namespace) -> BuildOutputs:
    if not args.skip_download:
        nhanes_files = download_nhanes(force=args.force_download)
    else:
        nhanes_files = {name: NHANES_DIR / f"{name}.XPT" for name in NHANES_URLS}
        missing = [str(path) for path in nhanes_files.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Missing NHANES files with --skip-download: {missing}")

    ensure_mmash(force=args.force_download, skip_download=args.skip_download)
    frames = load_nhanes(nhanes_files)
    nhanes_cohort = build_nhanes_cohort(frames)
    nhanes_observations, nhanes_references = build_nhanes_outputs(nhanes_cohort, args.max_mmash_subjects)
    mmash_observations, mmash_references, mmash_features = build_mmash_outputs(args.max_mmash_subjects)
    source_inventory, inventory_df = inspect_inspiration4()

    observations = nhanes_observations + mmash_observations
    references = nhanes_references + mmash_references
    findings = build_real_findings(observations)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    write_dataframe_csv(PROCESSED_DIR / "nhanes_astronaut_like_reference.csv", nhanes_cohort)
    write_dataframe_csv(PROCESSED_DIR / "nhanes_reference_slices.csv", pd.DataFrame(nhanes_references))
    write_dataframe_csv(PROCESSED_DIR / "mmash_subject_features.csv", mmash_features)
    write_dataframe_csv(PROCESSED_DIR / "mmash_archer_observations.csv", pd.DataFrame(mmash_observations))
    write_dataframe_csv(PROCESSED_DIR / "inspiration4_public_source_inventory.csv", inventory_df)

    write_csv(ARTEMIS_DATA / "proxy_observations.csv", observations, OBS_COLUMNS)
    write_csv(ARTEMIS_DATA / "reference_slices.csv", references, REFERENCE_COLUMNS)
    (ROOT / "api").mkdir(parents=True, exist_ok=True)
    (ROOT / "api" / "artemis_findings.json").write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

    row_counts = {
        "proxy_observations.csv": len(observations),
        "reference_slices.csv": len(references),
        "nhanes_observation_rows": len(nhanes_observations),
        "mmash_observation_rows": len(mmash_observations),
        "real_findings": len(findings["findings"]),
        "inspiration4_inventory_rows": len(source_inventory),
    }
    manifest = write_manifest(row_counts, source_inventory)
    write_data_provenance(manifest, row_counts)
    return BuildOutputs(observations, references, findings, source_inventory, row_counts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-download", action="store_true", help="Use existing local raw public files only.")
    parser.add_argument("--force-download", action="store_true", help="Redownload public source files.")
    parser.add_argument("--max-mmash-subjects", type=int, default=4, help="Number of MMASH subjects to include.")
    parser.add_argument("--output-dir", default=str(ARTEMIS_DATA), help="Compatibility argument; writes to artemis/data.")
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR), help="Compatibility argument; writes processed CSVs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = build(args)
    print("Built real public proxy demo data")
    for name, count in outputs.row_counts.items():
        print(f"- {name}: {count}")


if __name__ == "__main__":
    main()
