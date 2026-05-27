from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def tracked_files() -> list[str]:
    try:
        return subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        excluded = {".git", ".pytest_cache", "__pycache__"}
        return [
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*")
            if path.is_file() and not any(part in excluded for part in path.relative_to(ROOT).parts)
        ]


def test_public_demo_inputs_and_outputs_exist() -> None:
    required = [
        "README.md",
        "VERSION",
        "artemis/README.md",
        "artemis/run_demo.py",
        "scripts/build_real_proxy_demo_data.py",
        "api/artemis_findings.json",
        "artemis/data/proxy_observations.csv",
        "artemis/data/reference_slices.csv",
        "artemis/data/source_manifest.json",
        "artemis/output/finding_atlas.csv",
        "artemis/output/submission_summary.md",
    ]
    for relative in required:
        path = ROOT / relative
        assert path.exists(), relative
        assert path.stat().st_size > 0, relative


def test_public_repo_has_no_submission_packet_artifacts() -> None:
    forbidden_prefixes = (
        "submission-packets/",
        "submission-package/",
        "docs/submission/",
        "docs/qa/",
        "docs/security/",
        "docs/plans/",
    )
    forbidden_names = {
        "scripts/build_submission_package.py",
    }
    offenders = [
        path
        for path in tracked_files()
        if path in forbidden_names or path.startswith(forbidden_prefixes)
    ]
    assert offenders == []


def test_public_repo_has_no_tracked_raw_source_data() -> None:
    forbidden_parts = {
        ("data", "raw"),
        ("data", "processed"),
        ("data", "proxy", "nhanes"),
        ("data", "proxy", "physionet"),
        ("data", "proxy", "inspiration4"),
    }
    forbidden_suffixes = {".xpt", ".parquet", ".edf", ".pem", ".key", ".env"}
    offenders: list[str] = []
    for tracked_path in tracked_files():
        path = ROOT / tracked_path
        lower_parts = tuple(part.lower() for part in Path(tracked_path).parts)
        if any(lower_parts[: len(parts)] == parts for parts in forbidden_parts):
            offenders.append(tracked_path)
        if path.suffix.lower() in forbidden_suffixes:
            offenders.append(tracked_path)

    assert offenders == []
