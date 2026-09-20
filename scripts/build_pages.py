"""종목_히스토리.xlsx + theme_list.txt -> GitHub Pages 배포용 _site/ 생성.

pages/ 의 정적 파일을 _site/ 로 복사하고, _site/data/ 에 JSON을 만든다.
GitHub Actions(.github/workflows/pages.yml)와 로컬 확인에서 동일하게 사용한다.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "종목_히스토리.xlsx"
THEMES = ROOT / "theme_list.txt"
PAGES = ROOT / "pages"
OUT = ROOT / "_site"

NAME_COL = "종목명"
# JSON 키 -> 엑셀 컬럼. light.json 에 들어가는 것과 개별 파일로 나뉘는 것을 구분한다.
LIGHT = {"core": "코어테마", "all": "전체테마", "leader": "대장이력"}
HEAVY = {"article": "기사", "keyword": "키워드요약", "body": "기사본문", "kswing": "K스윙 정리"}
MIN_ROWS = 100


def clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace("_x000D_", "\n")


def read_themes() -> list[str]:
    if not THEMES.exists():
        return []
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            lines = [ln.strip() for ln in THEMES.read_text(encoding=encoding).splitlines()]
        except UnicodeDecodeError:
            continue
        themes = [ln for ln in lines if ln]
        if themes:
            return themes
    return []


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    if not XLSX.exists():
        sys.exit(f"[build_pages] 엑셀 없음: {XLSX}")

    df = pd.read_excel(XLSX, engine="openpyxl")
    needed = [NAME_COL, *LIGHT.values(), *HEAVY.values()]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        sys.exit(f"[build_pages] 필요한 컬럼이 없음: {missing} / 실제 컬럼: {list(df.columns)}")

    names_raw = df[NAME_COL].map(clean).str.strip()
    df = df[names_raw != ""].copy()
    df[NAME_COL] = names_raw[names_raw != ""]
    if len(df) < MIN_ROWS:
        sys.exit(f"[build_pages] 행이 너무 적음({len(df)}) — 잘못된 파일로 보고 중단")

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(PAGES, OUT)
    data_dir = OUT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    kst = timezone(timedelta(hours=9))
    light = {"built": datetime.now(kst).strftime("%Y-%m-%d %H:%M KST"), "names": df[NAME_COL].tolist()}
    for key, col in LIGHT.items():
        light[key] = [clean(v) for v in df[col]]
    write_json(data_dir / "light.json", light)

    for key, col in HEAVY.items():
        write_json(data_dir / f"{key}.json", [clean(v) for v in df[col]])

    write_json(data_dir / "themes.json", read_themes())

    total = sum(p.stat().st_size for p in data_dir.iterdir())
    print(f"[build_pages] 종목 {len(df):,}개, 테마 {len(read_themes()):,}개, data/ {total / 1024 / 1024:.1f}MB -> {OUT}")


if __name__ == "__main__":
    main()
