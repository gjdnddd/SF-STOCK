from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from normalize_case_events import (
    DATASET_ID,
    PROJECT_ID,
    TABLE_ID,
    parse_workbook,
    upload_rows,
)


def default_input_path() -> Path:
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir.parent / "종목_히스토리.xlsx",
        Path.home()
        / "OneDrive"
        / "2. 노후준비"
        / "1.2. 주식"
        / "2. 유목민"
        / "종목 히스토리"
        / "종목_히스토리.xlsx",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect local workbook changes and sync new case_events rows to BigQuery."
    )
    parser.add_argument(
        "--input",
        default=str(default_input_path()),
        help="Workbook path. Defaults to ../종목_히스토리.xlsx or the known OneDrive workbook path.",
    )
    parser.add_argument(
        "--project",
        default=PROJECT_ID,
        help=f"GCP project ID. Default: {PROJECT_ID}",
    )
    parser.add_argument(
        "--snapshot",
        default=str(Path(__file__).resolve().parent / "snapshot_case_ids.json"),
        help="Snapshot JSON path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect new rows without uploading to BigQuery or updating the snapshot.",
    )
    parser.add_argument(
        "--init-snapshot",
        action="store_true",
        help="Initialize the snapshot from current BigQuery case_ids.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_snapshot(snapshot_path: Path) -> dict[str, Any]:
    if not snapshot_path.exists():
        return {"last_sync": None, "case_ids": []}

    with snapshot_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    case_ids = payload.get("case_ids") or []
    if not isinstance(case_ids, list):
        raise ValueError("snapshot_case_ids.json must contain a list in case_ids.")

    return {
        "last_sync": payload.get("last_sync"),
        "case_ids": case_ids,
    }


def save_snapshot(snapshot_path: Path, case_ids: set[str]) -> None:
    payload = {
        "last_sync": now_iso(),
        "case_ids": sorted(case_ids),
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with snapshot_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def get_bigquery_client(project: str) -> Any:
    from google.cloud import bigquery

    return bigquery.Client(project=project)


def fetch_case_ids_from_bigquery(client: Any) -> set[str]:
    query = f"SELECT case_id FROM `{client.project}.{DATASET_ID}.{TABLE_ID}`"
    return {row["case_id"] for row in client.query(query).result()}


def initialize_snapshot(project: str, snapshot_path: Path) -> None:
    client = get_bigquery_client(project)
    case_ids = fetch_case_ids_from_bigquery(client)
    save_snapshot(snapshot_path, case_ids)
    print(f"[local_sync] 스냅샷 초기화 완료: {len(case_ids):,} case_ids")
    print(f"[local_sync] 저장 위치: {snapshot_path}")


def detect_new_rows(input_path: Path, snapshot_case_ids: set[str]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    parsed_rows = parse_workbook(input_path)
    new_rows = [row for row in parsed_rows if str(row["case_id"]) not in snapshot_case_ids]
    return parsed_rows, new_rows


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    snapshot_path = Path(args.snapshot).expanduser().resolve()

    if args.init_snapshot:
        initialize_snapshot(args.project, snapshot_path)
        return

    if not input_path.exists():
        raise FileNotFoundError(f"Input workbook not found: {input_path}")

    snapshot = load_snapshot(snapshot_path)
    snapshot_case_ids = set(snapshot["case_ids"])

    parsed_rows, new_rows = detect_new_rows(input_path, snapshot_case_ids)
    print(f"[local_sync] 엑셀 파싱 완료: {len(parsed_rows):,} rows")
    print(f"[local_sync] 스냅샷 로드: {len(snapshot_case_ids):,} case_ids")

    if not new_rows:
        print("[local_sync] 변경 없음")
        return

    print(f"[local_sync] 신규 감지: {len(new_rows):,} rows")
    if args.dry_run:
        print("[local_sync] dry-run: 업로드와 스냅샷 갱신을 건너뜁니다")
        return

    client = get_bigquery_client(args.project)
    print("[local_sync] BigQuery 업로드 중...")
    upload_rows(client, new_rows)

    updated_case_ids = snapshot_case_ids | {str(row["case_id"]) for row in new_rows}
    save_snapshot(snapshot_path, updated_case_ids)
    print(f"[local_sync] 완료: {len(new_rows):,} rows inserted / 스냅샷 갱신")


if __name__ == "__main__":
    main()
