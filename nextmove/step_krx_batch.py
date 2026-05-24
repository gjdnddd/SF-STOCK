"""
step_krx_batch.py: KRX Open API로 case_events 데이터 배치 채우기

채우는 항목:
  - rise_rate    : D0 등락률 (%)
  - trade_amount : D0 거래대금 (억원)
  - market_cond  : 지수 등락률 기반 상승/하락/횡보
  - d1~d5_return : D+1~D+5 종가 기준 수익률 (%)

실행:
  python nextmove/step_krx_batch.py --dry-run   # 채울 대상만 확인
  python nextmove/step_krx_batch.py             # 실제 채우기
  python nextmove/step_krx_batch.py --limit 100 # 100건만 처리
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date, timedelta
from typing import Optional

import requests
from google.cloud import bigquery

PROJECT_ID = "infin-stock-bot"
DATASET_ID = "nextmove_master"
TABLE_ID = "case_events"

KRX_AUTH_KEY = os.environ.get("KRX_AUTH_KEY", "")

# KRX Open API endpoints
KRX_KOSPI_URL = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
KRX_KOSDAQ_URL = "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd"
# 지수는 pykrx로 조회 (KRX 지수 endpoint 불안정)


# ============================================================================
# KRX Open API 조회
# ============================================================================

def fetch_krx_daily(base_date: str, market: str = "KOSPI") -> list[dict]:
    """
    KRX Open API로 특정 날짜의 전종목 일봉 조회.

    Args:
        base_date: 'YYYYMMDD' 형식
        market: 'KOSPI' 또는 'KOSDAQ'

    Returns:
        [{ISU_NM(종목명), TDD_CLSPRC(종가), FLUC_RT(등락률), ACC_TRDVAL(거래대금)}, ...]
    """
    if not KRX_AUTH_KEY:
        raise EnvironmentError("KRX_AUTH_KEY 환경변수가 설정되지 않았습니다.")

    url = KRX_KOSPI_URL if market == "KOSPI" else KRX_KOSDAQ_URL
    headers = {"AUTH_KEY": KRX_AUTH_KEY}
    params = {"basDd": base_date}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("OutBlock_1", [])
    except Exception as e:
        print(f"  ⚠️ KRX {market} 조회 실패 ({base_date}): {e}")
        return []


def fetch_krx_index(base_date: str) -> Optional[float]:
    """
    KOSPI 지수 등락률 조회 → market_cond 판단용.
    pykrx 사용 (KRX 지수 API endpoint 불안정).

    Returns:
        등락률 (%) 또는 None
    """
    try:
        from pykrx import stock as pykrx_stock
        frame = pykrx_stock.get_index_ohlcv_by_date(base_date, base_date, "1001")
        if frame.empty:
            return None
        row = frame.iloc[0]
        if "등락률" in frame.columns:
            return float(row["등락률"])
        if "종가" in frame.columns and "시가" in frame.columns:
            o, c = float(row["시가"]), float(row["종가"])
            return round((c - o) / o * 100, 2) if o else None
    except Exception as e:
        print(f"  ⚠️ pykrx 지수 조회 실패 ({base_date}): {e}")
    return None


def market_cond_from_rate(rate: Optional[float]) -> Optional[str]:
    if rate is None:
        return None
    if rate >= 0.5:
        return "상승"
    elif rate <= -0.5:
        return "하락"
    return "횡보"


def date_to_krx(d: date) -> str:
    return d.strftime("%Y%m%d")


def next_trading_days(base_date: date, n: int = 5) -> list[date]:
    """base_date 이후 n개 거래일(토/일 제외) 반환."""
    days = []
    current = base_date + timedelta(days=1)
    while len(days) < n:
        if current.weekday() < 5:  # 월~금
            days.append(current)
        current += timedelta(days=1)
    return days


# ============================================================================
# BigQuery 조회/업데이트
# ============================================================================

def fetch_null_rows(client: bigquery.Client, limit: int) -> list[dict]:
    """
    rise_rate 또는 d1_return이 NULL인 rows 조회.
    (이미 채워진 건 skip)
    """
    query = f"""
    SELECT case_id, event_date, stock_name
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    WHERE rise_rate IS NULL OR d1_return IS NULL
    ORDER BY event_date ASC
    LIMIT {limit}
    """
    rows = list(client.query(query).result())
    return [
        {
            "case_id": r["case_id"],
            "event_date": r["event_date"],
            "stock_name": r["stock_name"],
        }
        for r in rows
    ]


def update_row(client: bigquery.Client, case_id: str, values: dict) -> None:
    """단건 UPDATE."""
    set_clauses = ", ".join(
        f"{col} = {v if v is not None else 'NULL'}"
        for col, v in values.items()
    )
    query = f"""
    UPDATE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    SET {set_clauses}
    WHERE case_id = '{case_id}'
    """
    client.query(query).result()


# ============================================================================
# 메인 배치 처리
# ============================================================================

def process_date(
    client: bigquery.Client,
    target_date: date,
    rows_on_date: list[dict],
    dry_run: bool,
) -> int:
    """
    특정 날짜의 rows들을 KRX API로 조회해서 채움.

    Returns:
        처리된 rows 수
    """
    base_str = date_to_krx(target_date)
    print(f"\n[{base_str}] {len(rows_on_date)}개 종목 처리 중...")

    # KRX 전종목 일봉 조회 (KOSPI + KOSDAQ)
    kospi_data = fetch_krx_daily(base_str, "KOSPI")
    kosdaq_data = fetch_krx_daily(base_str, "KOSDAQ")
    all_stocks = kospi_data + kosdaq_data
    time.sleep(0.3)  # API 부하 방지

    # 종목명 → 데이터 매핑
    stock_map: dict[str, dict] = {}
    for item in all_stocks:
        name = item.get("ISU_NM", "").strip()
        if name:
            stock_map[name] = item

    # 지수 등락률 → market_cond
    index_rate = fetch_krx_index(base_str)
    market_cond = market_cond_from_rate(index_rate)
    time.sleep(0.3)

    # D+1~D+5 날짜 및 종가 조회
    trading_days = next_trading_days(target_date, 5)
    future_maps: list[dict[str, dict]] = []
    for td in trading_days:
        td_str = date_to_krx(td)
        k = fetch_krx_daily(td_str, "KOSPI")
        q = fetch_krx_daily(td_str, "KOSDAQ")
        future_map: dict[str, dict] = {}
        for item in k + q:
            name = item.get("ISU_NM", "").strip()
            if name:
                future_map[name] = item
        future_maps.append(future_map)
        time.sleep(0.2)

    updated = 0
    for row in rows_on_date:
        stock_name = row["stock_name"]
        case_id = row["case_id"]
        stock_data = stock_map.get(stock_name)

        # D0 데이터
        rise_rate = None
        trade_amount = None
        if stock_data:
            try:
                rise_rate = float(stock_data.get("FLUC_RT", "").replace(",", "") or 0)
            except ValueError:
                pass
            try:
                raw_val = stock_data.get("ACC_TRDVAL", "").replace(",", "") or "0"
                trade_amount = round(float(raw_val) / 100_000_000, 2)  # 원 → 억원
            except ValueError:
                pass

        # D+1~D+5 수익률 계산
        d_returns: list[Optional[float]] = []
        d0_close = None
        if stock_data:
            try:
                d0_close = float(stock_data.get("TDD_CLSPRC", "").replace(",", "") or 0) or None
            except ValueError:
                pass

        for fm in future_maps:
            future_data = fm.get(stock_name)
            if future_data and d0_close:
                try:
                    close = float(future_data.get("TDD_CLSPRC", "").replace(",", "") or 0)
                    ret = round((close - d0_close) / d0_close * 100, 2) if d0_close else None
                    d_returns.append(ret)
                except ValueError:
                    d_returns.append(None)
            else:
                d_returns.append(None)

        # 5개 보장
        while len(d_returns) < 5:
            d_returns.append(None)

        values = {
            "rise_rate": rise_rate,
            "trade_amount": trade_amount,
            "market_cond": f"'{market_cond}'" if market_cond else "NULL",
            "d1_return": d_returns[0],
            "d2_return": d_returns[1],
            "d3_return": d_returns[2],
            "d4_return": d_returns[3],
            "d5_return": d_returns[4],
        }

        if dry_run:
            print(f"  [DRY] {stock_name}: rise={rise_rate}, amt={trade_amount}, "
                  f"d1={d_returns[0]}, d5={d_returns[4]}")
        else:
            try:
                update_row(client, case_id, values)
                updated += 1
                print(f"  ✅ {stock_name}: rise={rise_rate}%, amt={trade_amount}억, "
                      f"d1={d_returns[0]}%")
            except Exception as e:
                print(f"  ❌ {stock_name} UPDATE 실패: {e}")

    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="KRX Open API 배치 채우기")
    parser.add_argument("--project", default=PROJECT_ID)
    parser.add_argument("--limit", type=int, default=500, help="처리할 최대 rows 수 (기본 500)")
    parser.add_argument("--dry-run", action="store_true", help="조회만, UPDATE 없음")
    args = parser.parse_args()

    if not KRX_AUTH_KEY:
        print("❌ KRX_AUTH_KEY 환경변수가 없습니다. ~/.bashrc 확인 후 source ~/.bashrc 실행하세요.")
        return

    client = bigquery.Client(project=args.project)

    print(f"[KRX 배치] NULL rows 조회 중 (최대 {args.limit}건)...")
    null_rows = fetch_null_rows(client, args.limit)

    if not null_rows:
        print("[KRX 배치] 채울 데이터 없음. 완료.")
        return

    print(f"[KRX 배치] 대상: {len(null_rows)}건")

    # 날짜별로 그룹핑 (같은 날짜는 API 1번만 호출)
    from collections import defaultdict
    date_groups: dict[date, list[dict]] = defaultdict(list)
    for row in null_rows:
        date_groups[row["event_date"]].append(row)

    total_updated = 0
    for target_date, rows in sorted(date_groups.items()):
        updated = process_date(client, target_date, rows, args.dry_run)
        total_updated += updated

    mode = "DRY-RUN" if args.dry_run else "완료"
    print(f"\n[KRX 배치] {mode}: {total_updated}건 업데이트")


if __name__ == "__main__":
    main()
