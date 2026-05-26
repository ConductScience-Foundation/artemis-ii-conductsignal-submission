"""Download primary proxy datasets for the Artemis II demo.

The script intentionally stores raw data under data/raw/primary_demo, which is
ignored by Git. It downloads only open, no-credential files:

- NHANES 2017-2018 XPT files from CDC.
- PhysioNet MMASH ZIP and extracted contents.
- Selected non-restricted Inspiration4 processed tabular files from NASA OSDR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


NHANES_FILES = {
    "DEMO_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.xpt",
    "BMX_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BMX_J.xpt",
    "CBC_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/CBC_J.xpt",
    "BIOPRO_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BIOPRO_J.xpt",
    "SMQ_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/SMQ_J.xpt",
    "PAQ_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/PAQ_J.xpt",
}

PHYSIONET_MMASH_URL = "https://physionet.org/files/mmash/1.0.0/MMASH.zip"

OSDR_STUDIES = {
    "OSD-569": [
        "OSD-569_metadata_OSD-569-ISA.zip",
        "LSDS-7_Complete_Blood_Count_CBC_TRANSFORMED.csv",
    ],
    "OSD-575": [
        "OSD-575_metadata_OSD-575-ISA.zip",
        "LSDS-8_Comprehensive_Metabolic_Panel_CMP_TRANSFORMED.csv",
        "LSDS-8_Multiplex_serum_immune_EvePanel_TRANSFORMED.csv",
        "LSDS-8_Multiplex_serum_cardiovascular_EvePanel_TRANSFORMED.csv",
        "LSDS-8_Multiplex_serum.immune.AlamarPanel_TRANSFORMED.csv",
    ],
    "OSD-656": [
        "OSD-656_metadata_OSD-656-ISA.zip",
        "LSDS-64_Multiplex_urine.immune.AlamarPanel_TRANSFORMED.csv",
    ],
}

OSDR_FILES_API = "https://osdr.nasa.gov/osdr/data/osd/files/{study_id}"
OSDR_DOWNLOAD_BASE = "https://osdr.nasa.gov"


@dataclass
class DownloadRecord:
    dataset: str
    source_url: str
    path: str
    bytes: int
    sha256: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, dataset: str, force: bool = False) -> DownloadRecord:
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError(f"Refusing non-HTTPS source URL: {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if force or not destination.exists():
        print(f"Downloading {url}")
        # URL scheme is validated above before this request is made.
        with urllib.request.urlopen(url) as response, destination.open("wb") as handle:  # nosec B310
            shutil.copyfileobj(response, handle)
    else:
        print(f"Using existing {destination}")

    return DownloadRecord(
        dataset=dataset,
        source_url=url,
        path=str(destination),
        bytes=destination.stat().st_size,
        sha256=sha256_file(destination),
    )


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"Unsafe zip member path: {member.filename}")
        archive.extractall(destination)


def load_json(url: str) -> dict:
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError(f"Refusing non-HTTPS source URL: {url}")
    # URL scheme is validated above before this request is made.
    with urllib.request.urlopen(url) as response:  # nosec B310
        return json.loads(response.read().decode("utf-8"))


def osdr_file_map(study: str) -> dict[str, str]:
    numeric_id = study.replace("OSD-", "")
    payload = load_json(OSDR_FILES_API.format(study_id=numeric_id))
    files = payload["studies"][study]["study_files"]
    mapping = {}
    for item in files:
        if item.get("restricted"):
            continue
        remote_url = item.get("remote_url")
        if remote_url:
            mapping[item["file_name"]] = urllib.parse.urljoin(OSDR_DOWNLOAD_BASE, remote_url)
    return mapping


def download_nhanes(base_dir: Path, force: bool) -> list[DownloadRecord]:
    records = []
    for filename, url in NHANES_FILES.items():
        records.append(download(url, base_dir / "nhanes" / filename, dataset="nhanes", force=force))
    return records


def download_physionet(base_dir: Path, force: bool) -> list[DownloadRecord]:
    zip_path = base_dir / "physionet" / "mmash" / "MMASH.zip"
    record = download(PHYSIONET_MMASH_URL, zip_path, dataset="physionet_mmash", force=force)
    extract_dir = base_dir / "physionet" / "mmash" / "extracted"
    if force and extract_dir.exists():
        shutil.rmtree(extract_dir)
    if not extract_dir.exists():
        print(f"Extracting {zip_path}")
        safe_extract_zip(zip_path, extract_dir)
    else:
        print(f"Using existing extraction {extract_dir}")
    return [record]


def download_osdr(base_dir: Path, force: bool) -> list[DownloadRecord]:
    records = []
    for study, filenames in OSDR_STUDIES.items():
        available = osdr_file_map(study)
        for filename in filenames:
            if filename not in available:
                raise KeyError(f"{filename} not found as non-restricted file in {study}")
            records.append(
                download(
                    available[filename],
                    base_dir / "inspiration4" / study / filename,
                    dataset=f"inspiration4_{study}",
                    force=force,
                )
            )
    return records


def write_manifest(base_dir: Path, records: Iterable[DownloadRecord]) -> None:
    manifest = {
        "generated_by": "scripts/download_primary_demo_data.py",
        "raw_data_root": str(base_dir),
        "records": [asdict(record) for record in records],
    }
    manifest_path = base_dir / "download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root() / "data" / "raw" / "primary_demo",
        help="Directory for raw downloaded data. Defaults to data/raw/primary_demo.",
    )
    parser.add_argument("--force", action="store_true", help="Re-download existing files.")
    args = parser.parse_args(argv)

    records: list[DownloadRecord] = []
    records.extend(download_nhanes(args.output_dir, force=args.force))
    records.extend(download_physionet(args.output_dir, force=args.force))
    records.extend(download_osdr(args.output_dir, force=args.force))
    write_manifest(args.output_dir, records)

    print(f"Downloaded/verified {len(records)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
