"""
VM측 파이프라인 래퍼 — web/app.py가 업로드한 /tmp/nm_web_args.json을 읽고 실행
stdout이 그대로 web UI에 표시됨
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ARGS_FILE = Path("/tmp/nm_web_args.json")

if not ARGS_FILE.exists():
    print("[ERROR] /tmp/nm_web_args.json 없음", flush=True)
    sys.exit(1)

args = json.loads(ARGS_FILE.read_text(encoding="utf-8"))

sys.path.insert(0, "/home/gjdnddd/SF-STOCK/nextmove")
from run_pipeline import pipeline_individual, pipeline_theme  # noqa: E402

mode = args.get("mode", "individual")

if mode == "individual":
    pipeline_individual(
        stock_name=args.get("stock_name", ""),
        title=args.get("title", ""),
        body=args.get("body", ""),
        stock_code=args.get("stock_code", ""),
        project_id="infin-stock-bot",
        skip_filter=False,
        chart_filter=args.get("chart_filter", False),
        json_output=False,
        override_theme=args.get("override_theme", ""),
    )
else:
    pipeline_theme(
        core_theme=args.get("core_theme", ""),
        themes_raw=args.get("themes", args.get("core_theme", "")),
        title=args.get("title", ""),
        body=args.get("body", ""),
        project_id="infin-stock-bot",
        skip_filter=False,
        chart_filter=args.get("chart_filter", False),
        json_output=False,
        strong_threshold=2,
    )
