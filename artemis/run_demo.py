"""Generate ConductScience Artemis II public demo artifacts.

The runner is dependency-free and deterministic. It reads normalized public
proxy CSV inputs, computes analysis tables, preserves the generated findings
JSON summary path, and updates the public demo output directory.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import shutil
from datetime import UTC, datetime
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from textwrap import shorten


ROOT = Path.cwd()
if not (ROOT / "artemis" / "data" / "proxy_observations.csv").exists():
    ROOT = Path(__file__).absolute().parents[1]

FINDINGS_INPUT = ROOT / "api" / "artemis_findings.json"
DATA_DIR = ROOT / "artemis" / "data"
OBSERVATIONS_INPUT = DATA_DIR / "proxy_observations.csv"
REFERENCES_INPUT = DATA_DIR / "reference_slices.csv"
SOURCE_MANIFEST_INPUT = DATA_DIR / "source_manifest.json"
OUTPUT_DIR = ROOT / "artemis" / "output"
WEB_DEMO_DIR = ROOT / "web" / "public" / "artemis" / "demo"

SCRIPT_VERSION = "0.4.1"
SOURCE_URLS = {
    "NHANES 2017-2018": "https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/overview.aspx?BeginYear=2017",
    "MMASH on PhysioNet": "https://physionet.org/content/mmash/1.0.0/",
    "NASA OSDR Inspiration4": "https://www.nasa.gov/osdr-latest-news-i4-mission-datasets/",
    "SOMA Nature Atlas": "https://www.nature.com/articles/s41586-024-07639-y",
}


@dataclass(frozen=True)
class CrewSummary:
    astronaut: str
    finding_count: int
    strongest_score: float
    mean_score: float
    max_abs_effect: float
    modalities: str
    change_point_count: int
    missing_count: int
    strongest_claim: str


@dataclass(frozen=True)
class Observation:
    subject_id: str
    modality: str
    variable: str
    phase: str
    time_point: int
    value: float
    unit: str
    source_dataset: str
    is_missing: bool
    missing_reason: str
    provenance: str


@dataclass(frozen=True)
class BaselineStats:
    subject_id: str
    variable: str
    modality: str
    baseline_n: int
    center: float
    spread: float
    stability: str
    provenance: str


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_findings(path: Path) -> dict:
    data = load_json(path)
    required = {"meta", "astronauts", "phases", "findings"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"Input file is missing required keys: {sorted(missing)}")
    return data


def load_observations(path: Path) -> list[Observation]:
    observations: list[Observation] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            observations.append(
                Observation(
                    subject_id=row["subject_id"],
                    modality=row["modality"],
                    variable=row["variable"],
                    phase=row["phase"],
                    time_point=int(row["time_point"]),
                    value=float(row["value"]),
                    unit=row["unit"],
                    source_dataset=row["source_dataset"],
                    is_missing=row["is_missing"].strip().lower() == "yes",
                    missing_reason=row["missing_reason"],
                    provenance=row["provenance"],
                )
            )
    return observations


def load_references(path: Path) -> dict[str, dict]:
    references: dict[str, dict] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            references[row["variable"]] = {
                "reference_dataset": row["reference_dataset"],
                "reference_filter": row["reference_filter"],
                "values": [float(value) for value in row["values"].split("|")],
                "unit": row["unit"],
                "source_url": row["source_url"],
                "provenance": row["provenance"],
            }
    return references


def group_observations(observations: list[Observation]) -> dict[tuple[str, str], list[Observation]]:
    groups: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        groups[(obs.subject_id, obs.variable)].append(obs)
    return {key: sorted(value, key=lambda obs: obs.time_point) for key, value in groups.items()}


def robust_spread(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0
    med = median(values)
    deviations = [abs(value - med) for value in values]
    mad = median(deviations)
    floor = max(abs(med) * 0.25, 0.05)
    if mad > 0:
        return max(mad * 1.4826, floor)
    span = max(values) - min(values)
    return max(span / 2, floor) if span > 0 else max(1.0, floor)


def baseline_stability(values: list[float], spread: float) -> str:
    if len(values) < 2:
        return "limited"
    center = median(values)
    denom = abs(center) if abs(center) > 1e-9 else 1.0
    cv = spread / denom
    if cv <= 0.15:
        return "stable"
    if cv <= 0.35:
        return "limited"
    return "unstable"


def compute_baselines(groups: dict[tuple[str, str], list[Observation]]) -> dict[tuple[str, str], BaselineStats]:
    baselines = {}
    for key, observations in groups.items():
        baseline_obs = [obs for obs in observations if obs.phase == "pre" and not obs.is_missing]
        values = [obs.value for obs in baseline_obs]
        modality = observations[0].modality
        if values:
            center = median(values)
            spread = robust_spread(values)
            stability = baseline_stability(values, spread)
        else:
            center = 0.0
            spread = 1.0
            stability = "not_applicable"
        baselines[key] = BaselineStats(
            subject_id=key[0],
            variable=key[1],
            modality=modality,
            baseline_n=len(values),
            center=center,
            spread=spread,
            stability=stability,
            provenance="; ".join(sorted({obs.provenance for obs in baseline_obs})) or "no personal baseline",
        )
    return baselines


def empirical_percentile(value: float, reference_values: list[float]) -> float:
    if not reference_values:
        return math.nan
    below_or_equal = sum(1 for item in reference_values if item <= value)
    return 100.0 * below_or_equal / len(reference_values)


def data_quality(obs: Observation, baseline: BaselineStats) -> str:
    if obs.is_missing:
        return "missing"
    if baseline.baseline_n < 2:
        return "limited_baseline"
    if baseline.stability == "unstable":
        return "unstable_baseline"
    return "ok"


def compute_baseline_rows(baselines: dict[tuple[str, str], BaselineStats]) -> list[dict]:
    rows = []
    for baseline in sorted(baselines.values(), key=lambda item: (item.subject_id, item.variable)):
        rows.append(
            {
                "subject_id": baseline.subject_id,
                "variable": baseline.variable,
                "modality": baseline.modality,
                "baseline_n": str(baseline.baseline_n),
                "baseline_center": f"{baseline.center:.4f}",
                "baseline_spread": f"{baseline.spread:.4f}",
                "baseline_stability": baseline.stability,
                "provenance": baseline.provenance,
            }
        )
    return rows


def compute_change_rows(
    groups: dict[tuple[str, str], list[Observation]],
    baselines: dict[tuple[str, str], BaselineStats],
) -> list[dict]:
    rows = []
    for key, observations in sorted(groups.items()):
        baseline = baselines[key]
        spread = baseline.spread if baseline.spread > 0 else 1.0
        for obs in observations:
            delta = obs.value - baseline.center
            robust_z = delta / spread
            ci_half_width = 1.96 / math.sqrt(max(1, baseline.baseline_n))
            rows.append(
                {
                    "subject_id": obs.subject_id,
                    "variable": obs.variable,
                    "phase": obs.phase,
                    "time_point": str(obs.time_point),
                    "delta_from_baseline": f"{delta:.4f}",
                    "robust_z": f"{robust_z:.4f}",
                    "effect_size": f"{robust_z:.4f}",
                    "ci_low": f"{robust_z - ci_half_width:.4f}",
                    "ci_high": f"{robust_z + ci_half_width:.4f}",
                    "data_quality": data_quality(obs, baseline),
                }
            )
    return rows


def compute_reference_rows(
    groups: dict[tuple[str, str], list[Observation]],
    references: dict[str, dict],
) -> list[dict]:
    rows = []
    for key, observations in sorted(groups.items()):
        subject_id, variable = key
        reference = references.get(variable)
        observed = [obs for obs in observations if not obs.is_missing]
        if not reference:
            rows.append(
                {
                    "subject_id": subject_id,
                    "variable": variable,
                    "reference_dataset": "not mapped",
                    "reference_filter": "not mapped",
                    "reference_percentile": "",
                    "mapping_status": "not_mapped",
                    "provenance": "no defensible reference slice in Phase 1",
                }
            )
            continue
        peak = max(observed, key=lambda obs: abs(obs.value - median([item.value for item in observed])))
        percentile = empirical_percentile(peak.value, reference["values"])
        rows.append(
            {
                "subject_id": subject_id,
                "variable": variable,
                "reference_dataset": reference["reference_dataset"],
                "reference_filter": reference["reference_filter"],
                "reference_percentile": f"{percentile:.1f}",
                "mapping_status": "mapped",
                "provenance": reference["provenance"],
            }
        )
    return rows


def compute_change_point_rows(
    groups: dict[tuple[str, str], list[Observation]],
    baselines: dict[tuple[str, str], BaselineStats],
) -> list[dict]:
    rows = []
    for key, observations in sorted(groups.items()):
        usable = [obs for obs in observations if not obs.is_missing]
        if len(usable) < 5:
            continue
        baseline = baselines[key]
        spread = baseline.spread if baseline.spread > 0 else 1.0
        best = None
        for split_idx in range(2, len(usable) - 1):
            before = usable[:split_idx]
            after = usable[split_idx:]
            before_mean = mean([obs.value for obs in before])
            after_mean = mean([obs.value for obs in after])
            effect = abs(after_mean - before_mean) / spread
            if best is None or effect > best["effect"]:
                best = {
                    "effect": effect,
                    "time_point": usable[split_idx].time_point,
                    "phase": usable[split_idx].phase,
                    "before": before_mean,
                    "after": after_mean,
                    "provenance": usable[split_idx].provenance,
                }
        if best is None or best["effect"] < 1.0:
            continue
        confidence = min(0.99, best["effect"] / (best["effect"] + 1.0))
        rows.append(
            {
                "subject_id": key[0],
                "variable": key[1],
                "phase": best["phase"],
                "change_time_point": str(best["time_point"]),
                "confidence": f"{confidence:.3f}",
                "segment_before": f"{best['before']:.4f}",
                "segment_after": f"{best['after']:.4f}",
                "method": "standard-library two-window mean-shift heuristic",
                "provenance": best["provenance"],
            }
        )
    return rows


def compute_recovery_rows(
    groups: dict[tuple[str, str], list[Observation]],
    baselines: dict[tuple[str, str], BaselineStats],
) -> list[dict]:
    rows = []
    for key, observations in sorted(groups.items()):
        baseline = baselines[key]
        spread = baseline.spread if baseline.spread > 0 else 1.0
        usable = [obs for obs in observations if not obs.is_missing]
        if not usable:
            continue
        effects = [(obs, (obs.value - baseline.center) / spread) for obs in usable]
        peak_obs, peak_effect = max(effects, key=lambda item: abs(item[1]))
        last_obs, last_effect = max(effects, key=lambda item: item[0].time_point)
        recovery_status = "returned_to_baseline" if abs(last_effect) < 1 else "recovering"
        if abs(last_effect) >= abs(peak_effect) * 0.8 and last_obs.phase == "post":
            recovery_status = "persistent"
        if len(effects) >= 2:
            first_post = next((item for item in effects if item[0].phase == "post"), effects[-2])
            denom = max(1, last_obs.time_point - first_post[0].time_point)
            slope = (last_effect - first_post[1]) / denom
        else:
            slope = 0.0
        rows.append(
            {
                "subject_id": key[0],
                "variable": key[1],
                "peak_phase": peak_obs.phase,
                "peak_effect": f"{peak_effect:.4f}",
                "last_observed_effect": f"{last_effect:.4f}",
                "recovery_status": recovery_status,
                "slope_estimate": f"{slope:.4f}",
                "provenance": peak_obs.provenance,
            }
        )
    return rows


def compute_concordance_rows(change_rows: list[dict], observations: list[Observation]) -> list[dict]:
    source_by_key = {
        (obs.subject_id, obs.variable): (obs.modality, obs.provenance)
        for obs in observations
    }
    strong_by_subject_phase: dict[tuple[str, str], list[tuple[str, str, float]]] = defaultdict(list)
    for row in change_rows:
        effect = abs(float(row["effect_size"]))
        if effect < 1.0 or row["data_quality"] == "missing":
            continue
        subject = row["subject_id"]
        phase = row["phase"]
        variable = row["variable"]
        modality = source_by_key.get((subject, variable), ("unknown", ""))[0]
        strong_by_subject_phase[(subject, phase)].append((variable, modality, effect))

    rows = []
    for (subject, phase), items in sorted(strong_by_subject_phase.items()):
        modalities = sorted({item[1] for item in items})
        if len(modalities) < 2:
            continue
        variables = sorted({item[0] for item in items})
        link_strength = mean([item[2] for item in items])
        rows.append(
            {
                "subject_id": subject,
                "phase": phase,
                "window_start": phase,
                "window_end": phase,
                "variables": "|".join(variables),
                "modalities": "|".join(modalities),
                "link_strength": f"{link_strength:.4f}",
                "claim_guardrail": "Temporal concordance only; no causal inference.",
            }
        )
    return rows


def effect_summary(finding: dict) -> tuple[str, float]:
    effects = finding.get("evidence", {}).get("effects", [])
    if not effects:
        return "", 0.0
    parts = []
    max_abs = 0.0
    for effect in effects:
        variable = effect.get("variable", "")
        d_value = float(effect.get("d", 0.0))
        ci = effect.get("ci", ["", ""])
        max_abs = max(max_abs, abs(d_value))
        parts.append(f"{variable}: d={d_value:.2f} [{ci[0]}, {ci[1]}]")
    return "; ".join(parts), max_abs


def change_point_summary(finding: dict) -> tuple[str, int]:
    change_points = finding.get("evidence", {}).get("change_points", [])
    parts = []
    for point in change_points:
        variables = ", ".join(point.get("variables", []))
        parts.append(
            f"day {point.get('day')} ({float(point.get('confidence', 0.0)):.2f}; {variables})"
        )
    return "; ".join(parts), len(change_points)


def cross_modal_summary(finding: dict) -> tuple[str, int]:
    links = finding.get("evidence", {}).get("cross_modal_links", [])
    parts = []
    for link in links:
        parts.append(
            f"{link.get('from')}->{link.get('to')}: r={float(link.get('correlation', 0.0)):.2f}"
        )
    return "; ".join(parts), len(links)


def missingness_summary(finding: dict) -> tuple[str, int]:
    missing = finding.get("trace", {}).get("missing", {})
    parts = []
    total = 0
    for variable, days in sorted(missing.items()):
        days = days or []
        total += len(days)
        parts.append(f"{variable}: {','.join(str(day) for day in days)}")
    return "; ".join(parts), total


def index_rows(rows: list[dict], key_fields: tuple[str, ...]) -> dict[tuple[str, ...], dict]:
    indexed = {}
    for row in rows:
        indexed[tuple(row[field] for field in key_fields)] = row
    return indexed


def build_finding_rows(
    data: dict,
    baseline_rows: list[dict],
    reference_rows: list[dict],
) -> list[dict]:
    baseline_by_subject_variable = index_rows(baseline_rows, ("subject_id", "variable"))
    reference_by_subject_variable = index_rows(reference_rows, ("subject_id", "variable"))
    rows = []
    for finding in sorted(data["findings"], key=lambda item: item["prominence_score"], reverse=True):
        effects, max_abs_effect = effect_summary(finding)
        change_points, change_point_count = change_point_summary(finding)
        cross_modal_links, cross_modal_count = cross_modal_summary(finding)
        missingness, missing_count = missingness_summary(finding)
        primary_variable = finding.get("evidence", {}).get("effects", [{}])[0].get("variable", "")
        baseline = baseline_by_subject_variable.get((finding["astronaut"], primary_variable), {})
        reference = reference_by_subject_variable.get((finding["astronaut"], primary_variable), {})
        rows.append(
            {
                "id": finding["id"],
                "astronaut": finding["astronaut"],
                "phase": finding["phase"],
                "zone": finding["zone"],
                "studies": "|".join(finding.get("studies", [])),
                "prominence_score": f"{float(finding['prominence_score']):.3f}",
                "max_abs_effect": f"{max_abs_effect:.3f}",
                "baseline_n": baseline.get("baseline_n", ""),
                "baseline_stability": baseline.get("baseline_stability", "not_available"),
                "reference_percentile": reference.get("reference_percentile", ""),
                "reference_anchor": reference.get("reference_dataset", "not mapped"),
                "change_point_count": str(change_point_count),
                "cross_modal_link_count": str(cross_modal_count),
                "missing_count": str(missing_count),
                "data_quality": "review_missingness" if missing_count else "ok",
                "guardrail_note": "Review priority for individual trajectory interpretation.",
                "effects": effects,
                "change_points": change_points,
                "cross_modal_links": cross_modal_links,
                "missingness": missingness,
                "source_dataset": reference.get("reference_dataset", "public proxy atlas finding"),
                "provenance": baseline.get("provenance", "api/artemis_findings.json"),
                "claim": finding["claim"],
            }
        )
    return rows


def build_crew_summary(data: dict) -> list[CrewSummary]:
    summaries = []
    for astronaut in data["astronauts"]:
        findings = [item for item in data["findings"] if item["astronaut"] == astronaut]
        if not findings:
            continue
        strongest = max(findings, key=lambda item: item["prominence_score"])
        scores = [float(item["prominence_score"]) for item in findings]
        max_abs_effect = 0.0
        modalities = set()
        change_points = 0
        missing = 0
        for finding in findings:
            modalities.update(finding.get("studies", []))
            _, finding_max_abs = effect_summary(finding)
            _, cp_count = change_point_summary(finding)
            _, missing_count = missingness_summary(finding)
            max_abs_effect = max(max_abs_effect, finding_max_abs)
            change_points += cp_count
            missing += missing_count
        summaries.append(
            CrewSummary(
                astronaut=astronaut,
                finding_count=len(findings),
                strongest_score=max(scores),
                mean_score=sum(scores) / len(scores),
                max_abs_effect=max_abs_effect,
                modalities=", ".join(sorted(modalities)),
                change_point_count=change_points,
                missing_count=missing,
                strongest_claim=strongest["claim"],
            )
        )
    return summaries


def build_missingness_rows(data: dict) -> list[dict]:
    rows = []
    for finding in data["findings"]:
        missing = finding.get("trace", {}).get("missing", {})
        for variable, days in sorted(missing.items()):
            rows.append(
                {
                    "finding_id": finding["id"],
                    "astronaut": finding["astronaut"],
                    "phase": finding["phase"],
                    "variable": variable,
                    "missing_time_points": "|".join(str(day) for day in days),
                    "missing_count": str(len(days)),
                }
            )
    return rows


def build_trace_rows(data: dict) -> list[dict]:
    rows = []
    for finding in data["findings"]:
        timeseries = finding.get("trace", {}).get("timeseries", {})
        missing = finding.get("trace", {}).get("missing", {})
        for variable, points in sorted(timeseries.items()):
            missing_days = set(missing.get(variable, []))
            for day, value in points:
                rows.append(
                    {
                        "finding_id": finding["id"],
                        "astronaut": finding["astronaut"],
                        "phase": finding["phase"],
                        "zone": finding["zone"],
                        "variable": variable,
                        "time_point": str(day),
                        "value": str(value),
                        "marked_missing": "yes" if day in missing_days else "no",
                    }
                )
    return rows


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None and rows:
        fieldnames = list(rows[0].keys())
    if not rows:
        path.write_text(",".join(fieldnames or []) + "\n", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_crew_summary_csv(path: Path, summaries: list[CrewSummary]) -> None:
    rows = [
        {
            "astronaut": item.astronaut,
            "finding_count": str(item.finding_count),
            "strongest_score": f"{item.strongest_score:.3f}",
            "mean_score": f"{item.mean_score:.3f}",
            "max_abs_effect": f"{item.max_abs_effect:.3f}",
            "modalities": item.modalities,
            "change_point_count": str(item.change_point_count),
            "missing_count": str(item.missing_count),
            "strongest_claim": item.strongest_claim,
        }
        for item in summaries
    ]
    write_csv(path, rows)


def svg_bar_chart(path: Path, title: str, labels: list[str], values: list[float], width: int = 980) -> None:
    row_h = 42
    left = 230
    right = 80
    top = 58
    height = top + row_h * len(labels) + 36
    max_value = max(values) if values else 1.0
    palette = ["#2f6fed", "#c37a00", "#188b63", "#cc3f64", "#6d5bd0", "#267f99"]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="34" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#172033">{html.escape(title)}</text>',
    ]
    for idx, (label, value) in enumerate(zip(labels, values)):
        y = top + idx * row_h
        bar_w = int((width - left - right) * (value / max_value))
        color = palette[idx % len(palette)]
        lines.append(
            f'<text x="24" y="{y + 23}" font-family="Arial, sans-serif" font-size="13" fill="#273244">{html.escape(label)}</text>'
        )
        lines.append(
            f'<rect x="{left}" y="{y + 6}" width="{bar_w}" height="24" rx="3" fill="{color}"/>'
        )
        lines.append(
            f'<text x="{left + bar_w + 10}" y="{y + 23}" font-family="Arial, sans-serif" font-size="13" fill="#273244">{value:.2f}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_figures(output_dir: Path, summaries: list[CrewSummary], finding_rows: list[dict]) -> None:
    svg_bar_chart(
        output_dir / "crew_state_summary.svg",
        "Crew-State Summary: strongest atlas score by astronaut",
        [
            f"{item.astronaut}: {shorten(item.strongest_claim, width=52, placeholder='...')}"
            for item in summaries
        ],
        [item.strongest_score for item in summaries],
    )
    top = finding_rows[:8]
    svg_bar_chart(
        output_dir / "top_findings.svg",
        "Top Atlas Findings: ranked review queue",
        [
            f"{row['astronaut']} {row['phase']}: {shorten(row['claim'], width=58, placeholder='...')}"
            for row in top
        ],
        [float(row["prominence_score"]) for row in top],
    )


def write_summary(
    path: Path,
    data: dict,
    manifest: dict,
    summaries: list[CrewSummary],
    finding_rows: list[dict],
    computed_counts: dict[str, int],
) -> None:
    top = finding_rows[0]
    lines = [
        "# ConductSignal Artemis II Demo Summary",
        "",
        f"Script version: {SCRIPT_VERSION}",
        f"Data phase: {manifest.get('phase', 'unknown')}",
        f"Input findings: {len(data['findings'])}",
        f"Crew members: {', '.join(data['astronauts'])}",
        f"Proxy datasets listed: {', '.join(data['meta'].get('datasets', []))}",
        "",
        "## Public Source Row Counts",
        "",
    ]
    for name, count in manifest.get("row_counts", {}).items():
        lines.append(f"- {name}: {count}")
    lines.extend(
        [
            "",
            "## Public Sources",
            "",
        ]
    )
    for source in manifest.get("sources", []):
        lines.append(f"- {source.get('name')}: {source.get('url')}")
    lines.extend(
        [
            "",
        "## Computed Phase 1 Tables",
        "",
        ]
    )
    for name, count in computed_counts.items():
        lines.append(f"- {name}: {count} rows")
    lines.extend(
        [
            "",
            "## Strongest Finding",
            "",
            f"- Finding: {top['id']}",
            f"- Astronaut: {top['astronaut']}",
            f"- Phase: {top['phase']}",
            f"- Score: {top['prominence_score']}",
            f"- Claim: {top['claim']}",
            "",
            "## Crew Summary",
            "",
            "| Astronaut | Findings | Strongest score | Max abs effect | Modalities | Change points | Missing values |",
            "|---|---:|---:|---:|---|---:|---:|",
        ]
    )
    for item in summaries:
        lines.append(
            f"| {item.astronaut} | {item.finding_count} | {item.strongest_score:.3f} | "
            f"{item.max_abs_effect:.3f} | {item.modalities} | {item.change_point_count} | {item.missing_count} |"
        )
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            manifest.get(
                "guardrail",
                "These outputs demonstrate method mechanics on public proxy data for Artemis II-style individual trajectory review.",
            ),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_method_provenance(output_dir: Path, output_files: list[Path]) -> None:
    manifest = load_json(SOURCE_MANIFEST_INPUT)
    source_urls = {source.get("name", ""): source.get("url", "") for source in manifest.get("sources", [])}
    provenance = {
        "script_version": SCRIPT_VERSION,
        "run_timestamp_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "guardrail": manifest.get("guardrail", ""),
        "input_files": {
            OBSERVATIONS_INPUT.relative_to(ROOT).as_posix(): file_sha256(OBSERVATIONS_INPUT),
            REFERENCES_INPUT.relative_to(ROOT).as_posix(): file_sha256(REFERENCES_INPUT),
            FINDINGS_INPUT.relative_to(ROOT).as_posix(): file_sha256(FINDINGS_INPUT),
            SOURCE_MANIFEST_INPUT.relative_to(ROOT).as_posix(): file_sha256(SOURCE_MANIFEST_INPUT),
        },
        "source_urls": source_urls or SOURCE_URLS,
        "algorithm_settings": {
            "phase": manifest.get("phase", "Phase 1 standard-library demo"),
            "baseline_center": "median",
            "baseline_spread": "MAD scaled by 1.4826, fallback span/2 or 1.0",
            "change_point": "two-window mean-shift heuristic, minimum 5 usable observations, effect threshold 1.0",
            "reference_anchor": "empirical percentile from curated reference slices",
            "concordance": "same-subject same-phase strong effects across at least two modalities",
        },
        "output_hashes": {
            path.relative_to(ROOT).as_posix(): file_sha256(path)
            for path in sorted(output_files)
            if path.exists() and path.name != "method_provenance.json"
        },
    }
    path = output_dir / "method_provenance.json"
    path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_public_artifacts(output_files: list[Path]) -> None:
    if WEB_DEMO_DIR.parent.exists():
        WEB_DEMO_DIR.mkdir(parents=True, exist_ok=True)
        for path in output_files:
            shutil.copy2(path, WEB_DEMO_DIR / path.name)


def main() -> None:
    data = load_findings(FINDINGS_INPUT)
    manifest = load_json(SOURCE_MANIFEST_INPUT)
    if manifest.get("phase") != "real_public_proxy_demo":
        raise ValueError("source_manifest.json must declare phase='real_public_proxy_demo' for this public demo")
    observations = load_observations(OBSERVATIONS_INPUT)
    references = load_references(REFERENCES_INPUT)
    groups = group_observations(observations)
    baselines = compute_baselines(groups)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    baseline_rows = compute_baseline_rows(baselines)
    change_rows = compute_change_rows(groups, baselines)
    reference_rows = compute_reference_rows(groups, references)
    change_point_rows = compute_change_point_rows(groups, baselines)
    recovery_rows = compute_recovery_rows(groups, baselines)
    concordance_rows = compute_concordance_rows(change_rows, observations)

    finding_rows = build_finding_rows(data, baseline_rows, reference_rows)
    crew_summaries = build_crew_summary(data)
    missingness_rows = build_missingness_rows(data)
    trace_rows = build_trace_rows(data)

    output_files = [
        OUTPUT_DIR / "baseline_table.csv",
        OUTPUT_DIR / "within_subject_change_table.csv",
        OUTPUT_DIR / "reference_anchor_table.csv",
        OUTPUT_DIR / "change_point_table.csv",
        OUTPUT_DIR / "recovery_table.csv",
        OUTPUT_DIR / "concordance_table.csv",
        OUTPUT_DIR / "finding_atlas.csv",
        OUTPUT_DIR / "crew_state_summary.csv",
        OUTPUT_DIR / "missingness_report.csv",
        OUTPUT_DIR / "trace_long.csv",
        OUTPUT_DIR / "crew_state_summary.svg",
        OUTPUT_DIR / "top_findings.svg",
        OUTPUT_DIR / "submission_summary.md",
    ]

    write_csv(OUTPUT_DIR / "baseline_table.csv", baseline_rows)
    write_csv(OUTPUT_DIR / "within_subject_change_table.csv", change_rows)
    write_csv(OUTPUT_DIR / "reference_anchor_table.csv", reference_rows)
    write_csv(OUTPUT_DIR / "change_point_table.csv", change_point_rows)
    write_csv(OUTPUT_DIR / "recovery_table.csv", recovery_rows)
    write_csv(OUTPUT_DIR / "concordance_table.csv", concordance_rows)
    write_csv(OUTPUT_DIR / "finding_atlas.csv", finding_rows)
    write_crew_summary_csv(OUTPUT_DIR / "crew_state_summary.csv", crew_summaries)
    write_csv(
        OUTPUT_DIR / "missingness_report.csv",
        missingness_rows,
        [
            "finding_id",
            "astronaut",
            "phase",
            "variable",
            "missing_time_points",
            "missing_count",
        ],
    )
    write_csv(OUTPUT_DIR / "trace_long.csv", trace_rows)
    write_figures(OUTPUT_DIR, crew_summaries, finding_rows)
    write_summary(
        OUTPUT_DIR / "submission_summary.md",
        data,
        manifest,
        crew_summaries,
        finding_rows,
        {
            "baseline_table.csv": len(baseline_rows),
            "within_subject_change_table.csv": len(change_rows),
            "reference_anchor_table.csv": len(reference_rows),
            "change_point_table.csv": len(change_point_rows),
            "recovery_table.csv": len(recovery_rows),
            "concordance_table.csv": len(concordance_rows),
        },
    )
    write_method_provenance(OUTPUT_DIR, output_files)
    output_files.append(OUTPUT_DIR / "method_provenance.json")
    copy_public_artifacts(output_files)

    print(f"Wrote {len(baseline_rows)} baseline rows")
    print(f"Wrote {len(change_rows)} within-subject change rows")
    print(f"Wrote {len(reference_rows)} reference anchor rows")
    print(f"Wrote {len(change_point_rows)} change-point rows")
    print(f"Wrote {len(recovery_rows)} recovery rows")
    print(f"Wrote {len(concordance_rows)} concordance rows")
    print(f"Wrote {len(finding_rows)} finding rows")
    print(f"Output: {OUTPUT_DIR}")
    if WEB_DEMO_DIR.exists():
        print(f"Web demo artifacts: {WEB_DEMO_DIR}")


if __name__ == "__main__":
    main()
