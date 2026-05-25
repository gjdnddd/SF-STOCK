"""
Step F: 편입 종목 추적 (predictions 테이블)

역할:
  - 파이프라인 PASS 종목 → predictions 테이블에 기록
  - D+1~D+8 실제 수익률 자동 업데이트 (배치)
  - 편출 조건 판단 (8일선 기준)
  - 성과 리포트

테이블: `infin-stock-bot.nextmove_master.predictions`
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, date, timedelta
from typing import Optional

from google.cloud import bigquery

PROJECT_ID = "infin-stock-bot"
DATASET_ID = "nextmove_master"
TABLE_ID = "predictions"
FULL_TABLE = f"`{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`"


# ============================================================================
# 테이블 생성
# ============================================================================

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {FULL_TABLE} (
  prediction_id   STRING  NOT NULL,
  created_at      TIMESTAMP NOT NULL,
  entry_date      DATE    NOT NULL,
  stock_code      STRING  NOT NULL,
  stock_name      STRING  NOT NULL,
  entry_price     FLOAT64,
  entry_volume    FLOAT64,
  trigger_title   STRING,
  trigger_type    STRING,
  core_theme      STRING,
  material_type   STRING,
  step_a_verdict  STRING,
  step_c_strength STRING,
  step_c_risk     STRING,
  step_e_verdict  STRING,
  step_e_score    INT64,
  ma8_at_entry    FLOAT64,
  ma20_at_entry   FLOAT64,
  high20_pct      FLOAT64,
  d1_actual       FLOAT64,
  d2_actual       FLOAT64,
  d3_actual       FLOAT64,
  d4_actual       FLOAT64,
  d5_actual       FLOAT64,
  d6_actual       FLOAT64,
  d7_actual       FLOAT64,
  d8_actual       FLOAT64,
  exit_date       DATE,
  exit_price      FLOAT64,
  exit_reason     STRING,
  realized_return FLOAT64,
  status          STRING NOT NULL,
  memo            STRING
)
OPTIONS (description = 'NextMove 편입 종목 예측 및 추적 테이블')
"""


def ensure_table(client: bigquery.Client) -> None:
    """predictions 테이블이 없으면 생성."""
    try:
        client.query(CREATE_TABLE_SQL).result()
        print("  ✅ predictions 테이블 확인/생성 완료")
    except Exception as e:
        print(f"  ⚠️ 테이블 생성 실패: {e}")


# ============================================================================
# 편입 기록
# ============================================================================

def add_prediction(
    client: bigquery.Client,
    stock_code: str,
    stock_name: str,
    entry_date: Optional[str] = None,     # YYYY-MM-DD, 기본 오늘
    trigger_title: str = "",
    trigger_type: str = "individual",     # 'individual' | 'theme'
    core_theme: str = "",
    step_a_result: Optional[dict] = None,
    step_c_result: Optional[dict] = None,
    step_e_result: Optional[dict] = None,
    memo: str = "",
) -> Optional[str]:
    """
    편입 종목 predictions 테이블에 기록.

    Returns:
        prediction_id (str) or None (실패 시)
    """
    if entry_date is None:
        entry_date = date.today().isoformat()

    pred_id = str(uuid.uuid4())[:16]  # 짧은 UUID
    now = datetime.utcnow().isoformat() + "Z"

    # Step A 정보
    step_a_verdict = None
    material_type = None
    if step_a_result:
        step_a_verdict = step_a_result.get("verdict")
        material_type = step_a_result.get("material_type")

    # Step C 정보
    step_c_strength = None
    step_c_risk = None
    if step_c_result:
        strength_data = step_c_result.get("strength", {})
        step_c_strength = strength_data.get("strength")
        step_c_risk = strength_data.get("momentum_risk")

    # Step E 정보
    step_e_verdict = None
    step_e_score = None
    ma8 = None
    ma20 = None
    high20_pct = None
    entry_volume = None
    if step_e_result:
        step_e_verdict = step_e_result.get("verdict")
        step_e_score = step_e_result.get("score")
        ma8 = step_e_result.get("ma8")
        ma20 = step_e_result.get("ma20")
        high20_pct = step_e_result.get("high20_pct")
        entry_volume = step_e_result.get("volume_today")

    # pykrx로 진입가 조회
    entry_price = _get_close_price(stock_code, entry_date)

    def _v(val):
        """None → 'NULL', 숫자 → 그대로, 문자 → 따옴표"""
        if val is None:
            return "NULL"
        if isinstance(val, str):
            escaped = val.replace("'", "\\'")
            return f"'{escaped}'"
        return str(val)

    query = f"""
    INSERT INTO {FULL_TABLE} (
      prediction_id, created_at, entry_date,
      stock_code, stock_name, entry_price, entry_volume,
      trigger_title, trigger_type, core_theme, material_type,
      step_a_verdict, step_c_strength, step_c_risk,
      step_e_verdict, step_e_score,
      ma8_at_entry, ma20_at_entry, high20_pct,
      status, memo
    ) VALUES (
      '{pred_id}', TIMESTAMP('{now}'), DATE('{entry_date}'),
      {_v(stock_code)}, {_v(stock_name)}, {_v(entry_price)}, {_v(entry_volume)},
      {_v(trigger_title)}, {_v(trigger_type)}, {_v(core_theme)}, {_v(material_type)},
      {_v(step_a_verdict)}, {_v(step_c_strength)}, {_v(step_c_risk)},
      {_v(step_e_verdict)}, {_v(step_e_score)},
      {_v(ma8)}, {_v(ma20)}, {_v(high20_pct)},
      'ACTIVE', {_v(memo)}
    )
    """

    try:
        client.query(query).result()
        print(f"  ✅ 편입 기록: {stock_name} ({stock_code}) [ID: {pred_id}]")
        return pred_id
    except Exception as e:
        print(f"  ❌ 편입 기록 실패: {e}")
        return None


def _get_close_price(stock_code: str, target_date: str) -> Optional[float]:
    """pykrx로 특정일 종가 조회."""
    try:
        from pykrx import stock
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        start = (dt - timedelta(days=5)).strftime("%Y%m%d")
        end = dt.strftime("%Y%m%d")
        df = stock.get_market_ohlcv_by_date(start, end, stock_code)
        if df is not None and not df.empty and '종가' in df.columns:
            return float(df['종가'].iloc[-1])
    except Exception:
        pass
    return None


# ============================================================================
# D+N 실제 수익률 업데이트 (배치용)
# ============================================================================

def update_actuals(client: bigquery.Client, prediction_id: str) -> None:
    """
    prediction_id의 D+1~D+8 실제 등락률 업데이트.
    entry_date 기준으로 각 D+N 영업일 종가 변화율 계산.
    """
    # 현재 레코드 조회
    query = f"""
    SELECT prediction_id, stock_code, entry_date, entry_price, status
    FROM {FULL_TABLE}
    WHERE prediction_id = '{prediction_id}'
    """
    rows = list(client.query(query).result())
    if not rows:
        print(f"  ⚠️ {prediction_id} 레코드 없음")
        return

    row = dict(rows[0])
    if row.get("status") == "CLOSED":
        return  # 이미 종료

    stock_code = row["stock_code"]
    entry_date = row["entry_date"]
    entry_price = row.get("entry_price")
    if not entry_price:
        return

    # pykrx로 이후 가격 조회
    try:
        from pykrx import stock
        start = entry_date.strftime("%Y%m%d")
        end = (entry_date + timedelta(days=20)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv_by_date(start, end, stock_code)
        if df is None or df.empty or '종가' in df.columns is False:
            return

        closes = df['종가'].tolist()
        if len(closes) < 2:
            return

        # D0은 closes[0], D+1은 closes[1], ...
        set_parts = []
        for n in range(1, 9):
            if len(closes) > n:
                ret = round((closes[n] - closes[0]) / closes[0] * 100, 2)
                set_parts.append(f"d{n}_actual = {ret}")

        if not set_parts:
            return

        update_sql = f"""
        UPDATE {FULL_TABLE}
        SET {', '.join(set_parts)}
        WHERE prediction_id = '{prediction_id}'
        """
        client.query(update_sql).result()
        print(f"  ✅ {prediction_id} D+1~D+{len(set_parts)} 업데이트")

    except Exception as e:
        print(f"  ⚠️ 수익률 업데이트 실패: {e}")


# ============================================================================
# 편출 판단 (8일선 기준)
# ============================================================================

def check_exit(
    client: bigquery.Client,
    prediction_id: str,
    ma_period: int = 8,
) -> Optional[dict]:
    """
    8일선 기준 편출 여부 판단.

    Returns:
        None (보유 유지) or {"exit": True, "reason": str, "exit_price": float}
    """
    query = f"""
    SELECT prediction_id, stock_code, stock_name, entry_date, entry_price, status
    FROM {FULL_TABLE}
    WHERE prediction_id = '{prediction_id}' AND status = 'ACTIVE'
    """
    rows = list(client.query(query).result())
    if not rows:
        return None

    row = dict(rows[0])
    stock_code = row["stock_code"]

    try:
        from pykrx import stock as krx
        today = date.today()
        start = (today - timedelta(days=ma_period * 3)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
        df = krx.get_market_ohlcv_by_date(start, end, stock_code)
        if df is None or df.empty or '종가' not in df.columns:
            return None

        closes = df['종가'].tolist()
        if len(closes) < ma_period:
            return None

        current_close = closes[-1]
        ma = sum(closes[-ma_period:]) / ma_period

        if current_close < ma:
            return {
                "exit": True,
                "reason": f"{ma_period}일선 이탈 ({current_close:,.0f} < MA{ma_period}: {ma:,.0f})",
                "exit_price": current_close,
            }
        return None  # 보유 유지

    except Exception as e:
        print(f"  ⚠️ 편출 판단 실패: {e}")
        return None


def close_prediction(
    client: bigquery.Client,
    prediction_id: str,
    exit_reason: str,
    exit_price: float,
    entry_price: Optional[float] = None,
) -> None:
    """편입 종목 편출 처리."""
    today = date.today().isoformat()

    realized = None
    if entry_price and exit_price:
        realized = round((exit_price - entry_price) / entry_price * 100, 2)

    realized_str = str(realized) if realized is not None else "NULL"
    price_str = str(exit_price) if exit_price else "NULL"

    query = f"""
    UPDATE {FULL_TABLE}
    SET
      status = 'CLOSED',
      exit_date = DATE('{today}'),
      exit_price = {price_str},
      exit_reason = '{exit_reason}',
      realized_return = {realized_str}
    WHERE prediction_id = '{prediction_id}'
    """
    try:
        client.query(query).result()
        ret_str = f"{realized:+.1f}%" if realized is not None else "N/A"
        print(f"  ✅ 편출 완료: {prediction_id}  {exit_reason}  {ret_str}")
    except Exception as e:
        print(f"  ❌ 편출 처리 실패: {e}")


# ============================================================================
# 조회
# ============================================================================

def list_active(client: bigquery.Client) -> list[dict]:
    """현재 보유 중인 종목 조회."""
    query = f"""
    SELECT
      prediction_id, entry_date, stock_name, stock_code,
      entry_price, step_c_strength, step_e_verdict,
      d1_actual, d3_actual, d5_actual, status, memo
    FROM {FULL_TABLE}
    WHERE status = 'ACTIVE'
    ORDER BY entry_date DESC
    """
    try:
        return [dict(r) for r in client.query(query).result()]
    except Exception as e:
        print(f"  ⚠️ 조회 실패: {e}")
        return []


def performance_report(client: bigquery.Client) -> dict:
    """전체 성과 요약."""
    query = f"""
    SELECT
      COUNT(*) as total,
      COUNTIF(status = 'ACTIVE') as active,
      COUNTIF(status = 'CLOSED') as closed,
      ROUND(AVG(IF(status='CLOSED', realized_return, NULL)), 2) as avg_return,
      ROUND(COUNTIF(status='CLOSED' AND realized_return > 0)
            / NULLIF(COUNTIF(status='CLOSED'), 0) * 100, 1) as win_rate,
      ROUND(AVG(d1_actual), 2) as d1_avg,
      ROUND(AVG(d5_actual), 2) as d5_avg
    FROM {FULL_TABLE}
    """
    try:
        rows = list(client.query(query).result())
        return dict(rows[0]) if rows else {}
    except Exception as e:
        print(f"  ⚠️ 성과 조회 실패: {e}")
        return {}


# ============================================================================
# 통합 실행
# ============================================================================

def run_step_f_add(
    stock_code: str,
    stock_name: str,
    trigger_title: str = "",
    trigger_type: str = "individual",
    core_theme: str = "",
    step_a_result: Optional[dict] = None,
    step_c_result: Optional[dict] = None,
    step_e_result: Optional[dict] = None,
    memo: str = "",
    project_id: str = PROJECT_ID,
) -> Optional[str]:
    """
    편입 기록 (파이프라인 마지막 단계에서 호출).

    Returns:
        prediction_id or None
    """
    client = bigquery.Client(project=project_id)
    ensure_table(client)
    return add_prediction(
        client=client,
        stock_code=stock_code,
        stock_name=stock_name,
        trigger_title=trigger_title,
        trigger_type=trigger_type,
        core_theme=core_theme,
        step_a_result=step_a_result,
        step_c_result=step_c_result,
        step_e_result=step_e_result,
        memo=memo,
    )


def run_step_f_report(project_id: str = PROJECT_ID) -> None:
    """현재 보유/성과 리포트 출력."""
    client = bigquery.Client(project=project_id)

    print("\n" + "=" * 60)
    print("NextMove predictions 현황")
    print("=" * 60)

    perf = performance_report(client)
    if perf:
        print(f"  전체: {perf.get('total', 0)}건  "
              f"보유: {perf.get('active', 0)}  종료: {perf.get('closed', 0)}")
        if perf.get('closed', 0) > 0:
            print(f"  실현 수익률 avg: {perf.get('avg_return', 'N/A')}%  "
                  f"승률: {perf.get('win_rate', 'N/A')}%")
        print(f"  D+1 avg: {perf.get('d1_avg', 'N/A')}%  "
              f"D+5 avg: {perf.get('d5_avg', 'N/A')}%")

    actives = list_active(client)
    if actives:
        print(f"\n  ─ 현재 보유 중 ({len(actives)}종목) ─")
        for r in actives:
            d1 = r.get('d1_actual')
            d5 = r.get('d5_actual')
            d1_str = f"D+1:{d1:+.1f}%" if d1 is not None else "D+1:N/A"
            d5_str = f"D+5:{d5:+.1f}%" if d5 is not None else ""
            print(f"  [{r['entry_date']}] {r['stock_name']:12s} "
                  f"{r.get('step_c_strength','?'):6s} "
                  f"{r.get('step_e_verdict','?'):4s}  "
                  f"{d1_str}  {d5_str}")
    else:
        print("\n  보유 종목 없음")
    print("=" * 60)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="predictions 테이블 관리")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="테이블 생성")
    sub.add_parser("report", help="현황 리포트")

    p_add = sub.add_parser("add", help="편입 기록")
    p_add.add_argument("--code", required=True, help="종목코드")
    p_add.add_argument("--name", required=True, help="종목명")
    p_add.add_argument("--title", default="", help="기사 제목")
    p_add.add_argument("--memo", default="")

    p_close = sub.add_parser("close", help="편출 처리")
    p_close.add_argument("--id", required=True, help="prediction_id")
    p_close.add_argument("--reason", default="수동")
    p_close.add_argument("--price", type=float, required=True)

    args = parser.parse_args()
    client = bigquery.Client(project=PROJECT_ID)

    if args.cmd == "init":
        ensure_table(client)

    elif args.cmd == "report":
        run_step_f_report()

    elif args.cmd == "add":
        ensure_table(client)
        pid = add_prediction(
            client=client,
            stock_code=args.code,
            stock_name=args.name,
            trigger_title=args.title,
            memo=args.memo,
        )
        if pid:
            print(f"prediction_id: {pid}")

    elif args.cmd == "close":
        close_prediction(
            client=client,
            prediction_id=args.id,
            exit_reason=args.reason,
            exit_price=args.price,
        )
