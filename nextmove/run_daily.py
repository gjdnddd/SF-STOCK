"""
run_daily.py — NextMove 일일 유지보수 배치

매일 장 마감 후 실행:
  1. ACTIVE predictions 전체 조회
  2. 각 prediction D+1~D+8 실제 수익률 업데이트 (update_actuals)
  3. 각 prediction 8일선 편출 조건 확인 (check_exit) → 충족 시 close_prediction
  4. 실행 결과 요약 출력
  5. 로그 파일 기록 (~/predictions_daily.log)

실행 방법:
  cd /home/gjdnddd/SF-STOCK/nextmove
  python3 run_daily.py
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path

from google.cloud import bigquery

from step_f_predictions import (
    check_exit,
    close_prediction,
    list_active,
    performance_report,
    update_actuals,
    PROJECT_ID,
)

LOG_FILE = Path.home() / "predictions_daily.log"


def log(msg: str, fp=None) -> None:
    """콘솔 + 로그 파일 동시 출력."""
    print(msg)
    if fp:
        fp.write(msg + "\n")


def run_daily() -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "a", encoding="utf-8") as fp:
        log(f"\n{'=' * 60}", fp)
        log(f"[run_daily] 실행: {now_str}", fp)
        log(f"{'=' * 60}", fp)

        try:
            client = bigquery.Client(project=PROJECT_ID)
        except Exception as e:
            log(f"[ERROR] BigQuery 클라이언트 생성 실패: {e}", fp)
            return

        # ── 1. ACTIVE predictions 조회 ────────────────────────────────────────
        actives = list_active(client)
        log(f"\n[1] ACTIVE predictions: {len(actives)}건", fp)

        if not actives:
            log("  보유 종목 없음 — 배치 종료", fp)
            _write_footer(fp, now_str, updated=0, exited=0)
            return

        for r in actives:
            log(
                f"  - [{r.get('entry_date')}] {r.get('stock_name')} "
                f"({r.get('stock_code')})  id={r.get('prediction_id')}",
                fp,
            )

        # ── 1.5. KIS 분봉 수집 (장 마감 후 ACTIVE 종목 전체) ─────────────────
        log(f"\n[1.5] KIS 분봉 수집 ...", fp)
        try:
            from step_kis_minute import run_collect as _kis_collect
            for r in actives:
                code = r.get("stock_code", "")
                name = r.get("stock_name", code)
                try:
                    bars = _kis_collect(code)
                    log(f"  {name} ({code}): {len(bars)}개 분봉 수집", fp)
                except Exception as e:
                    log(f"  [WARN] {name} 분봉 수집 실패: {e}", fp)
        except ImportError:
            log("  [SKIP] step_kis_minute 미설치 — 건너뜀", fp)
        except Exception as e:
            log(f"  [WARN] KIS 분봉 수집 오류: {e}", fp)

        # ── 2. D+1~D+8 실제 수익률 업데이트 ──────────────────────────────────
        log(f"\n[2] D+1~D+8 실제 수익률 업데이트 ...", fp)
        updated = 0
        for r in actives:
            pid = r.get("prediction_id")
            name = r.get("stock_name", pid)
            try:
                update_actuals(client, pid)
                updated += 1
            except Exception as e:
                log(f"  [WARN] {name} ({pid}) 업데이트 실패: {e}", fp)
                log("  " + traceback.format_exc().strip(), fp)

        log(f"  => 업데이트 완료: {updated}건", fp)

        # ── 3. 8일선 편출 조건 확인 ───────────────────────────────────────────
        log(f"\n[3] 8일선 편출 조건 확인 ...", fp)
        exited = 0
        for r in actives:
            pid = r.get("prediction_id")
            name = r.get("stock_name", pid)
            entry_price = r.get("entry_price")

            try:
                result = check_exit(client, pid, ma_period=8)
                if result and result.get("exit"):
                    reason = result["reason"]
                    exit_price = result["exit_price"]
                    log(f"  [편출] {name} ({pid}): {reason}", fp)
                    close_prediction(
                        client=client,
                        prediction_id=pid,
                        exit_reason=reason,
                        exit_price=exit_price,
                        entry_price=entry_price,
                    )
                    exited += 1
                else:
                    log(f"  [보유] {name} ({pid}): 편출 조건 미충족", fp)
            except Exception as e:
                log(f"  [WARN] {name} ({pid}) 편출 확인 실패: {e}", fp)
                log("  " + traceback.format_exc().strip(), fp)

        log(f"  => 편출 처리: {exited}건", fp)

        # ── 4. 성과 요약 ──────────────────────────────────────────────────────
        log(f"\n[4] 성과 요약", fp)
        try:
            perf = performance_report(client)
            if perf:
                log(
                    f"  전체: {perf.get('total', 0)}건  "
                    f"보유: {perf.get('active', 0)}  "
                    f"종료: {perf.get('closed', 0)}",
                    fp,
                )
                if perf.get("closed", 0) > 0:
                    log(
                        f"  실현 수익률 avg: {perf.get('avg_return', 'N/A')}%  "
                        f"승률: {perf.get('win_rate', 'N/A')}%",
                        fp,
                    )
                log(
                    f"  D+1 avg: {perf.get('d1_avg', 'N/A')}%  "
                    f"D+5 avg: {perf.get('d5_avg', 'N/A')}%",
                    fp,
                )
        except Exception as e:
            log(f"  [WARN] 성과 조회 실패: {e}", fp)

        _write_footer(fp, now_str, updated=updated, exited=exited)


def _write_footer(fp, now_str: str, updated: int, exited: int) -> None:
    summary = (
        f"\n[결과] {now_str} — 업데이트 {updated}건, 편출 {exited}건"
    )
    log(summary, fp)
    log("=" * 60, fp)


if __name__ == "__main__":
    run_daily()
