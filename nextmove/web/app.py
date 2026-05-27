"""
NextMove Web UI — Flask application
로컬 실행: python app.py  (포트 5000)
PC / 노트북 양쪽 접근 가능 (같은 네트워크)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path

import numpy as np
from flask import Flask, render_template, request

# ── 의존성 조건부 import ──────────────────────────────────────────

try:
    from pykrx import stock as krx
    PYKRX_OK = True
except ImportError:
    PYKRX_OK = False

try:
    from google.cloud import bigquery
    _BQ = bigquery.Client(project="infin-stock-bot")
    BQ_OK = True
except Exception:
    BQ_OK = False
    _BQ = None

# ── 상수 ─────────────────────────────────────────────────────────

PROJECT  = "infin-stock-bot"
DATASET  = "nextmove_master"
VM_USER  = "gjdnddd"
VM_NAME  = "infin-stock-bot"
VM_ZONE  = "us-central1-a"
VM_PATH  = "/home/gjdnddd/SF-STOCK/nextmove"

app = Flask(__name__)


# ══════════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════════

def get_ohlcv(stock_code: str, days: int = 30):
    """pykrx 일봉 조회 (최근 days일)"""
    if not PYKRX_OK or not stock_code:
        return None
    end   = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
    try:
        import pandas as pd
        df = krx.get_market_ohlcv_by_date(start, end, stock_code)
        df = df.dropna()
        return df.tail(days) if not df.empty else None
    except Exception:
        return None


def analyze_ohlc(df) -> dict:
    """일봉 OHLC 패턴 분석 — 3일선/전일종가/시가 반등 가능성 판단"""
    if df is None or len(df) < 2:
        return {}

    today = df.iloc[-1]
    prev  = df.iloc[-2]

    o  = float(today["시가"])
    h  = float(today["고가"])
    l  = float(today["저가"])
    c  = float(today["종가"])
    pc = float(prev["종가"])

    gap_pct     = round((o - pc) / pc * 100, 1) if pc else 0
    close_chg   = round((c - pc) / pc * 100, 1) if pc else 0
    high_from_o = round((h - o) / o * 100, 1)   if o else 0
    low_from_o  = round((l - o) / o * 100, 1)   if o else 0
    body_pos    = round((c - l) / (h - l) * 100, 1) if h != l else 50

    closes = df["종가"].astype(float).values
    ma3  = round(float(np.mean(closes[-3:])), 0) if len(closes) >= 3 else None
    ma8  = round(float(np.mean(closes[-8:])), 0) if len(closes) >= 8 else None
    ma20 = round(float(np.mean(closes[-20:])), 0) if len(closes) >= 20 else None

    above_ma3  = c >= ma3 if ma3 else True
    above_ma8  = c >= ma8 if ma8 else True
    above_open = c >= o

    # ── 신호 판단 ──────────────────────────────────────────────────
    if above_ma3 and body_pos >= 60:
        ma3_sig = ("✅", "MA3 위 고가권 마감 — 3일선 지지 가능성 높음")
    elif above_ma3:
        ma3_sig = ("🟡", "MA3 위 마감 — 3일선 지지 확인 중")
    elif ma3 and c >= ma3 * 0.98:
        ma3_sig = ("🟡", "MA3 근접 — 이탈 직전 주의")
    else:
        ma3_sig = ("❌", "MA3 이탈 — 3일선 반등 불투명")

    if close_chg >= 0 and body_pos >= 50:
        prev_sig = ("✅", "전일종가 상회 + 중상권 마감 — 전일종가 지지 가능")
    elif close_chg >= 0:
        prev_sig = ("🟡", "전일종가 상회 + 저가권 마감 — 전일종가 지지 불안정")
    else:
        prev_sig = ("❌", "전일종가 이탈 음봉 — 재반등 시 전일종가가 저항")

    if above_open and body_pos >= 70:
        open_sig = ("✅", "시가 상회 + 고가권 마감 — 내일 시가 지지 가능")
    elif above_open:
        open_sig = ("🟡", "시가 상회 마감 — 시가 지지 확인 필요")
    else:
        open_sig = ("❌", "시가 이탈 음봉 — 내일 갭하락 시 시가가 저항")

    score = sum([above_ma3, above_ma8, close_chg >= 0, above_open, body_pos >= 50])

    if score >= 4:
        verdict, vcolor = "HOLD",  "#27ae60"
    elif score >= 3:
        verdict, vcolor = "WATCH", "#e67e22"
    else:
        verdict, vcolor = "RISK",  "#e74c3c"

    return {
        "date":        str(df.index[-1].date()),
        "open":        int(o),   "high": int(h),
        "low":         int(l),   "close": int(c),
        "prev_close":  int(pc),
        "gap_pct":     gap_pct,
        "close_chg":   close_chg,
        "high_from_o": high_from_o,
        "low_from_o":  low_from_o,
        "body_pos":    body_pos,
        "ma3":         int(ma3)  if ma3  else None,
        "ma8":         int(ma8)  if ma8  else None,
        "ma20":        int(ma20) if ma20 else None,
        "ma3_signal":  ma3_sig,
        "prev_signal": prev_sig,
        "open_signal": open_sig,
        "verdict":     verdict,
        "vcolor":      vcolor,
        "score":       score,
    }


def bq_query(sql: str, params: list = None) -> list[dict]:
    if not BQ_OK:
        return []
    try:
        cfg = bigquery.QueryJobConfig(query_parameters=params) if params else None
        return [dict(r) for r in _BQ.query(sql, job_config=cfg).result()]
    except Exception as e:
        print(f"[BQ] 쿼리 오류: {e}")
        return []


# ══════════════════════════════════════════════════════════════════
# 라우트
# ══════════════════════════════════════════════════════════════════

@app.route("/")
def dashboard():
    rows = bq_query(f"""
        SELECT prediction_id, stock_code, stock_name, entry_date, entry_price,
               strategy_code, article_title,
               d1_return, d3_return, d5_return
        FROM `{PROJECT}.{DATASET}.predictions`
        WHERE status = 'ACTIVE'
        ORDER BY entry_date DESC
    """)

    enriched = []
    for r in rows:
        df       = get_ohlcv(r.get("stock_code", ""), days=20)
        analysis = analyze_ohlc(df) if df is not None else {}

        current_price = analysis.get("close")
        entry_price   = r.get("entry_price")
        cur_ret = None
        if current_price and entry_price:
            cur_ret = round((current_price - float(entry_price)) / float(entry_price) * 100, 2)

        enriched.append({**r, "analysis": analysis, "cur_ret": cur_ret})

    return render_template("dashboard.html",
        actives=enriched, bq_ok=BQ_OK, pykrx_ok=PYKRX_OK,
        today=date.today().isoformat())


@app.route("/tracking/<prediction_id>")
def tracking(prediction_id):
    rows = bq_query(
        f"SELECT * FROM `{PROJECT}.{DATASET}.predictions` WHERE prediction_id = @pid LIMIT 1",
        params=[bigquery.ScalarQueryParameter("pid", "STRING", prediction_id)] if BQ_OK else None,
    )
    if not rows:
        return "종목을 찾을 수 없습니다", 404

    pred = rows[0]
    code = pred.get("stock_code", "")

    df       = get_ohlcv(code, days=20)
    analysis = analyze_ohlc(df) if df is not None else {}

    ohlc_rows = []
    if df is not None and not df.empty:
        for idx, r in df.tail(7).iloc[::-1].iterrows():
            ohlc_rows.append({
                "date":   str(idx.date()),
                "open":   int(r["시가"]),
                "high":   int(r["고가"]),
                "low":    int(r["저가"]),
                "close":  int(r["종가"]),
                "volume": int(r["거래량"]),
            })

    current_price = analysis.get("close")
    entry_price   = pred.get("entry_price")
    cur_ret = None
    if current_price and entry_price:
        cur_ret = round((current_price - float(entry_price)) / float(entry_price) * 100, 2)

    return render_template("tracking.html",
        pred=pred, analysis=analysis, ohlc_rows=ohlc_rows, cur_ret=cur_ret)


@app.route("/performance")
def performance():
    rows = bq_query(f"""
        SELECT prediction_id, stock_code, stock_name, entry_date, entry_price,
               strategy_code, status,
               d1_return, d2_return, d3_return, d5_return,
               final_return, exit_date, exit_reason
        FROM `{PROJECT}.{DATASET}.predictions`
        ORDER BY entry_date DESC
        LIMIT 300
    """)

    total  = len(rows)
    active = sum(1 for r in rows if r.get("status") == "ACTIVE")
    closed = total - active

    closed_rows = [r for r in rows if r.get("status") == "CLOSED" and r.get("final_return") is not None]
    returns     = [float(r["final_return"]) for r in closed_rows]

    avg_return = round(sum(returns) / len(returns), 2) if returns else None
    win_rate   = round(sum(1 for x in returns if x > 0) / len(returns) * 100, 1) if returns else None

    dx_avgs = {}
    for d in [1, 2, 3, 5]:
        key  = f"d{d}_return"
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        dx_avgs[f"d{d}"] = round(sum(vals) / len(vals), 2) if vals else None

    strategy_map: dict[str, dict] = {}
    for r in closed_rows:
        sc = r.get("strategy_code") or "기타"
        if sc not in strategy_map:
            strategy_map[sc] = {"count": 0, "returns": []}
        strategy_map[sc]["count"] += 1
        ret = r.get("final_return")
        if ret is not None:
            strategy_map[sc]["returns"].append(float(ret))

    strategy_summary = sorted([
        {
            "code":       sc,
            "count":      d["count"],
            "avg_return": round(sum(d["returns"]) / len(d["returns"]), 2) if d["returns"] else None,
            "win_rate":   round(sum(1 for x in d["returns"] if x > 0) / len(d["returns"]) * 100, 1) if d["returns"] else None,
        }
        for sc, d in strategy_map.items()
    ], key=lambda x: (x.get("avg_return") or 0), reverse=True)

    return render_template("performance.html",
        rows=rows[:100], total=total, active=active, closed=closed,
        avg_return=avg_return, win_rate=win_rate,
        dx_avgs=dx_avgs, strategy_summary=strategy_summary)


@app.route("/pipeline", methods=["GET", "POST"])
def pipeline():
    result_text = None
    error       = None

    if request.method == "POST":
        mode      = request.form.get("mode", "individual")
        use_chart = request.form.get("chart_filter") == "on"

        args: dict = {
            "mode":         mode,
            "title":        request.form.get("title", ""),
            "body":         request.form.get("body", "")[:200],
            "chart_filter": use_chart,
        }
        if mode == "individual":
            args["stock_name"]     = request.form.get("stock_name", "")
            args["stock_code"]     = request.form.get("stock_code", "")
            args["override_theme"] = request.form.get("override_theme", "")
        else:
            args["core_theme"] = request.form.get("core_theme", "")
            args["themes"]     = request.form.get("themes", "")

        tmp_json = Path(tempfile.gettempdir()) / "nm_web_args.json"
        tmp_json.write_text(json.dumps(args, ensure_ascii=False), encoding="utf-8")

        try:
            # ── 1. VM에 인자 JSON 업로드 (한글 인코딩 문제 우회) ─────────────
            scp = subprocess.run(
                ["gcloud.cmd", "compute", "scp", str(tmp_json),
                 f"{VM_NAME}:/tmp/nm_web_args.json", f"--zone={VM_ZONE}"],
                capture_output=True, timeout=30,
            )
            if scp.returncode != 0:
                raise RuntimeError(f"SCP 실패: {scp.stderr.decode(errors='replace')}")

            # ── 2. VM에서 래퍼 스크립트 실행 ─────────────────────────────────
            inner = (
                f"source /home/{VM_USER}/.bashrc_env && "
                f"cd {VM_PATH} && "
                f"python3 web/run_wrapper.py"
            )
            ssh = subprocess.run(
                ["gcloud.cmd", "compute", "ssh", VM_NAME,
                 f"--zone={VM_ZONE}",
                 f"--command=sudo -H -u {VM_USER} bash -c '{inner}'"],
                capture_output=True, timeout=120,
                encoding="utf-8", errors="replace",
            )
            result_text = (ssh.stdout or "").strip()
            if ssh.returncode != 0 and not result_text:
                raise RuntimeError(ssh.stderr or "VM 실행 오류")

        except subprocess.TimeoutExpired:
            error = "실행 시간 초과 (120초) — VM 상태를 확인하세요."
        except Exception as e:
            error = str(e)
        finally:
            tmp_json.unlink(missing_ok=True)

    return render_template("pipeline.html", result_text=result_text, error=error)


if __name__ == "__main__":
    print(f"[NextMove Web] http://localhost:5000")
    print(f"  BigQuery: {'OK' if BQ_OK else '미연결'}")
    print(f"  pykrx   : {'OK' if PYKRX_OK else '미설치'}")
    app.run(host="0.0.0.0", port=5000, debug=False)
