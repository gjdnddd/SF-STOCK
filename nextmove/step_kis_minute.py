"""
KIS REST API 분봉 수집 → BigQuery minute_data 저장
장 마감 후 run_daily.py에서 ACTIVE 종목 자동 수집용
"""

from __future__ import annotations

import os
import time
import requests
from datetime import datetime, date, timedelta
from google.cloud import bigquery

KIS_BASE   = "https://openapi.koreainvestment.com:9443"
BQ_PROJECT = "infin-stock-bot"
BQ_DATASET = "nextmove_master"
BQ_TABLE   = "minute_data"


def _get_token(app_key: str, app_secret: str) -> str:
    r = requests.post(
        f"{KIS_BASE}/oauth2/tokenP",
        json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _fetch_bars(stock_code: str, from_time: str, token: str, app_key: str, app_secret: str) -> list:
    """단일 호출: from_time 이전 분봉 최대 30개 반환"""
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST03010200",
        "custtype": "P",
    }
    params = {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_HOUR_1": from_time,
        "FID_PW_DATA_INCU_YN": "Y",
    }
    r = requests.get(
        f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        headers=headers,
        params=params,
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("output2", [])


def collect_day_bars(
    stock_code: str,
    date_str: str,
    token: str,
    app_key: str,
    app_secret: str,
) -> list[dict]:
    """당일 전체 1분봉 수집 (09:00~15:30), 페이징 처리"""
    all_bars: list[dict] = []
    current_time = "153000"

    while True:
        bars = _fetch_bars(stock_code, current_time, token, app_key, app_secret)
        if not bars:
            break

        for b in bars:
            t = b.get("stck_cntg_hour", "")
            if t < "090000":
                return all_bars
            all_bars.append({
                "stock_code": stock_code,
                "date":       date_str,
                "bar_time":   f"{t[:2]}:{t[2:4]}:{t[4:6]}",
                "open":       float(b.get("stck_oprc", 0) or 0),
                "high":       float(b.get("stck_hgpr", 0) or 0),
                "low":        float(b.get("stck_lwpr", 0) or 0),
                "close":      float(b.get("stck_prpr", 0) or 0),
                "volume":     int(b.get("cntg_vol", 0) or 0),
            })

        last_t = bars[-1].get("stck_cntg_hour", "090000")
        if last_t <= "090000":
            break

        prev_dt = datetime.strptime(last_t, "%H%M%S") - timedelta(minutes=1)
        prev    = prev_dt.strftime("%H%M%S")
        if prev < "090000":
            break
        current_time = prev
        time.sleep(0.1)  # KIS API 호출 제한 여유

    return all_bars


def ensure_table(client: bigquery.Client) -> None:
    table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
    schema = [
        bigquery.SchemaField("stock_code", "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("date",       "DATE",    mode="REQUIRED"),
        bigquery.SchemaField("bar_time",   "TIME",    mode="REQUIRED"),
        bigquery.SchemaField("open",       "FLOAT64"),
        bigquery.SchemaField("high",       "FLOAT64"),
        bigquery.SchemaField("low",        "FLOAT64"),
        bigquery.SchemaField("close",      "FLOAT64"),
        bigquery.SchemaField("volume",     "INT64"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
    ]
    try:
        client.get_table(table_id)
    except Exception:
        table = bigquery.Table(table_id, schema=schema)
        table.clustering_fields = ["stock_code", "date"]
        client.create_table(table)
        print(f"[KIS] {BQ_TABLE} 테이블 생성 완료")


def upload_bars(bars: list[dict], client: bigquery.Client) -> None:
    if not bars:
        return
    table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
    now  = datetime.utcnow().isoformat()
    rows = [{**b, "created_at": now} for b in bars]
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        print(f"[KIS] BQ 업로드 오류: {errors}")
    else:
        print(f"[KIS] {len(bars)}개 분봉 업로드 완료")


def run_collect(stock_code: str, date_str: str | None = None) -> list[dict]:
    """외부(run_daily.py 등)에서 호출하는 메인 함수"""
    app_key    = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    if not date_str:
        date_str = date.today().strftime("%Y-%m-%d")

    print(f"[KIS] {stock_code} {date_str} 분봉 수집")
    token  = _get_token(app_key, app_secret)
    bars   = collect_day_bars(stock_code, date_str, token, app_key, app_secret)

    if not bars:
        print(f"[KIS] {stock_code} 분봉 데이터 없음 (휴장일 or 조회 오류)")
        return []

    client = bigquery.Client(project=BQ_PROJECT)
    ensure_table(client)
    upload_bars(bars, client)
    print(f"[KIS] {stock_code}: {len(bars)}개 수집 완료")
    return bars


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python step_kis_minute.py <stock_code> [YYYY-MM-DD]")
        sys.exit(1)
    run_collect(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
