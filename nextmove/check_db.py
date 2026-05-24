"""
check_db.py: BigQuery case_events 현황 빠른 확인

실행:
  python3 nextmove/check_db.py           # 전체 요약
  python3 nextmove/check_db.py --detail  # 컬럼별 NULL 비율 포함
  python3 nextmove/check_db.py --recent  # 최근 10건 샘플
"""

from __future__ import annotations

import argparse
import sys
from google.cloud import bigquery

PROJECT_ID = "infin-stock-bot"
DATASET_ID = "nextmove_master"
TABLE_ID = "case_events"


def get_client(project: str = PROJECT_ID) -> bigquery.Client:
    return bigquery.Client(project=project)


def run_query(client: bigquery.Client, sql: str) -> list[dict]:
    return [dict(row) for row in client.query(sql).result()]


def print_summary(client: bigquery.Client) -> None:
    print("\n[1] 기본 현황")
    rows = run_query(client, f"""
    SELECT
      COUNT(*) as total,
      COUNT(DISTINCT stock_name) as stocks,
      COUNT(DISTINCT DATE_TRUNC(event_date, YEAR)) as years,
      MIN(event_date) as min_date,
      MAX(event_date) as max_date
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    """)
    r = rows[0]
    print(f"  전체: {r['total']:,}건 / 종목: {r['stocks']:,}개")
    print(f"  기간: {str(r['min_date'])[:10]} ~ {str(r['max_date'])[:10]}")

    print("\n[2] KRX 데이터 채움 현황")
    rows2 = run_query(client, f"""
    SELECT
      COUNTIF(rise_rate IS NOT NULL) as rise_filled,
      COUNTIF(trade_amount IS NOT NULL) as amt_filled,
      COUNTIF(d1_return IS NOT NULL) as d1_filled,
      COUNTIF(d5_return IS NOT NULL) as d5_filled,
      COUNTIF(market_cond IS NOT NULL) as market_cond_filled,
      COUNT(*) as total
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    """)
    r2 = rows2[0]
    total = r2['total']
    pct = lambda n: f"{n:,} ({n/total*100:.1f}%)"
    print(f"  rise_rate:    {pct(r2['rise_filled'])}")
    print(f"  trade_amount: {pct(r2['amt_filled'])}")
    print(f"  d1_return:    {pct(r2['d1_filled'])}")
    print(f"  d5_return:    {pct(r2['d5_filled'])}")
    print(f"  market_cond:  {pct(r2['market_cond_filled'])}")


def print_detail(client: bigquery.Client) -> None:
    print("\n[3] 연도별 rise_rate 채움 현황")
    rows = run_query(client, f"""
    SELECT
      EXTRACT(YEAR FROM event_date) as year,
      COUNT(*) as total,
      COUNTIF(rise_rate IS NOT NULL) as filled
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    GROUP BY year
    ORDER BY year
    """)
    for r in rows:
        pct = r['filled'] / r['total'] * 100 if r['total'] else 0
        bar = "▓" * int(pct / 10) + "░" * (10 - int(pct / 10))
        print(f"  {r['year']}: {bar} {r['filled']:,}/{r['total']:,} ({pct:.0f}%)")


def print_recent(client: bigquery.Client) -> None:
    print("\n[4] 최근 10건 샘플 (rise_rate 있는 것)")
    rows = run_query(client, f"""
    SELECT
      stock_name, event_date, rise_rate, trade_amount,
      d1_return, d5_return, market_cond
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    WHERE rise_rate IS NOT NULL
    ORDER BY event_date DESC
    LIMIT 10
    """)
    for r in rows:
        date = str(r['event_date'])[:10]
        rise = f"{r['rise_rate']:+.1f}%" if r['rise_rate'] is not None else "N/A"
        amt = f"{r['trade_amount']:.0f}억" if r['trade_amount'] is not None else "N/A"
        d1 = f"{r['d1_return']:+.1f}%" if r['d1_return'] is not None else "N/A"
        d5 = f"{r['d5_return']:+.1f}%" if r['d5_return'] is not None else "N/A"
        print(f"  {date} | {r['stock_name']:<12} | D0:{rise:>7} | 거래대금:{amt:>8} "
              f"| D+1:{d1:>7} | D+5:{d5:>7}")


def print_top_stocks(client: bigquery.Client) -> None:
    print("\n[5] D+1 수익 TOP 10 종목 (rise_rate>5% 사례 10건 이상)")
    rows = run_query(client, f"""
    SELECT
      stock_name,
      COUNT(*) as case_cnt,
      AVG(d1_return) as d1_avg,
      AVG(d5_return) as d5_avg,
      COUNTIF(d1_return > 0) / COUNT(*) * 100 as d1_win_rate
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    WHERE rise_rate > 5
      AND d1_return IS NOT NULL
    GROUP BY stock_name
    HAVING COUNT(*) >= 10
    ORDER BY d1_avg DESC
    LIMIT 10
    """)
    for i, r in enumerate(rows, 1):
        d1 = f"{r['d1_avg']:+.1f}%" if r['d1_avg'] is not None else "N/A"
        d5 = f"{r['d5_avg']:+.1f}%" if r['d5_avg'] is not None else "N/A"
        wr = f"{r['d1_win_rate']:.0f}%" if r['d1_win_rate'] is not None else "N/A"
        print(f"  {i:2d}. {r['stock_name']:<12} | {r['case_cnt']}건 | "
              f"D+1:{d1:>7} | D+5:{d5:>7} | 승률:{wr}")


def main() -> None:
    parser = argparse.ArgumentParser(description="BigQuery case_events 현황 확인")
    parser.add_argument("--detail", action="store_true", help="연도별 채움 현황")
    parser.add_argument("--recent", action="store_true", help="최근 샘플 출력")
    parser.add_argument("--top", action="store_true", help="수익 TOP 종목 출력")
    parser.add_argument("--all", action="store_true", help="전체 리포트")
    parser.add_argument("--project", default=PROJECT_ID)
    args = parser.parse_args()

    try:
        client = get_client(args.project)
    except Exception as e:
        print(f"❌ BigQuery 연결 실패: {e}")
        sys.exit(1)

    print("=" * 60)
    print("NextMove DB 현황 리포트")
    print("=" * 60)

    print_summary(client)

    if args.detail or args.all:
        print_detail(client)
    if args.recent or args.all:
        print_recent(client)
    if args.top or args.all:
        print_top_stocks(client)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
