"""
Step C: 유사 사례 분석 (개별종목 / 테마 두 경로)

역할:
  경로 1 - 개별 종목 기사:
    - BigQuery에서 해당 종목의 과거 사례 조회
    - Claude Haiku: 현재 기사 vs 과거 기사 재료 세기 비교 → 강도 판단
    - 유사 과거 사례의 D+1~D+5 수익률 통계 산출

  경로 2 - 테마 기사:
    - Step B의 similar_cases (이미 테마 매칭된 과거 사례들) 수신
    - rise_rate > 기준치인 "강한 종목" 필터링
    - 종목별 D+1~D+5 평균 수익률 집계 → 빈도/수익 기준 랭킹

입력:
  run_step_c_individual(stock_name, title, body, step_a_result)
  run_step_c_theme(similar_cases)

출력:
  개별종목: {"article_type": "individual", "stock_name", "past_cases",
             "strength", "stats", "reference_count"}
  테마:     {"article_type": "theme", "strong_stocks", "top_by_d1",
             "top_by_d5", "theme_dates", "total_cases"}
"""

from __future__ import annotations

import json
import os
import statistics
from typing import Optional

import anthropic
from google.cloud import bigquery

PROJECT_ID = "infin-stock-bot"
DATASET_ID = "nextmove_master"
TABLE_ID = "case_events"

# 강한 종목 필터 기준 (등락률 %)
STRONG_STOCK_THRESHOLD = 3.0   # D0 등락률 > 3% → "강한 종목"
LEADER_STOCK_THRESHOLD = 7.0   # D0 등락률 > 7% → "대장 종목"


# ============================================================================
# 공통 유틸
# ============================================================================

def safe_float(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def compute_stats(returns: list[float]) -> dict:
    """수익률 리스트 → 통계 딕셔너리."""
    valid = [r for r in returns if r is not None]
    if not valid:
        return {"count": 0, "avg": None, "median": None,
                "win_rate": None, "max": None, "min": None}
    return {
        "count": len(valid),
        "avg": round(statistics.mean(valid), 2),
        "median": round(statistics.median(valid), 2),
        "win_rate": round(sum(1 for r in valid if r > 0) / len(valid) * 100, 1),
        "max": round(max(valid), 2),
        "min": round(min(valid), 2),
    }


def aggregate_dn_stats(cases: list[dict]) -> dict:
    """D1~D5 수익률 통계 집계."""
    return {
        f"d{n}": compute_stats([safe_float(c.get(f"d{n}_return")) for c in cases])
        for n in range(1, 6)
    }


# ============================================================================
# 경로 1: 개별 종목 기사
# ============================================================================

def fetch_stock_cases(stock_name: str, client: bigquery.Client) -> list[dict]:
    """
    BigQuery에서 특정 종목의 과거 사례 조회.
    rise_rate가 채워진 것 우선, 없으면 전체 반환.
    """
    query = f"""
    SELECT
      case_id, event_date, stock_name,
      article_title, article_body,
      market_cond, is_leader,
      rise_rate, trade_amount,
      d1_return, d2_return, d3_return, d4_return, d5_return,
      keyword_summary, master_memo
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    WHERE stock_name = @stock_name
    ORDER BY event_date DESC
    LIMIT 50
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("stock_name", "STRING", stock_name)
        ]
    )
    try:
        results = client.query(query, job_config=job_config).result()
        return [dict(row) for row in results]
    except Exception as e:
        print(f"  ⚠️ BigQuery 조회 실패: {e}")
        return []


STRENGTH_SYSTEM_PROMPT = """당신은 한국 단기 주식 모멘텀 투자 전문가입니다.
현재 기사와 과거 동일 종목 기사들을 비교해서 재료의 세기를 판단하세요.

## 판단 기준

### 재료 강도
- STRONG (강): 과거 유사 재료 대비 규모·임팩트가 크거나 신규성이 높음
- MEDIUM (보통): 과거와 비슷한 수준의 재료
- WEAK (약): 과거보다 임팩트가 작거나 반복 노출로 모멘텀 소진 우려

### 중요 고려 사항
- 같은 재료가 이미 여러 번 반복되었으면 모멘텀 소진 가능성 높음
- 과거 동일 재료에서 주가 반응이 약했다면 신뢰도 낮음
- 이번 재료가 과거보다 큰 금액/고객사/규모라면 강도 상향

## 출력 형식 (JSON만, 다른 텍스트 절대 금지)
{
  "strength": "STRONG" | "MEDIUM" | "WEAK",
  "reason": "판단 근거 (50자 이내)",
  "repeat_count": 유사재료 반복 횟수(int),
  "best_match_dates": ["YYYY-MM-DD", ...],  // 가장 유사한 과거 사례 날짜 최대 3개
  "momentum_risk": "HIGH" | "MEDIUM" | "LOW"  // 모멘텀 소진 위험도
}"""


def assess_strength_with_claude(
    stock_name: str,
    current_title: str,
    current_body: str,
    past_cases: list[dict],
    step_a_material_type: Optional[str] = None,
) -> dict:
    """
    Claude Haiku: 현재 기사 vs 과거 사례 재료 강도 비교.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # 과거 사례 요약 (최대 10개)
    past_summary = []
    for c in past_cases[:10]:
        date = str(c.get("event_date", ""))[:10]
        title = str(c.get("article_title", ""))[:60]
        rise = c.get("rise_rate")
        d1 = c.get("d1_return")
        rise_str = f"{rise:+.1f}%" if rise is not None else "미기록"
        d1_str = f"D+1={d1:+.1f}%" if d1 is not None else ""
        past_summary.append(f"  - {date}: {title} [D0:{rise_str} {d1_str}]")

    past_text = "\n".join(past_summary) if past_summary else "  (과거 사례 없음)"

    user_message = f"""종목: {stock_name}
재료 유형: {step_a_material_type or "미분류"}

[현재 기사]
제목: {current_title}
본문: {current_body[:300] if current_body else "(없음)"}

[과거 동일 종목 사례 {len(past_cases)}건]
{past_text}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=STRENGTH_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        text = response.content[0].text.strip()
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "strength": "MEDIUM",
            "reason": "Claude 응답 파싱 실패, 기본값 적용",
            "repeat_count": 0,
            "best_match_dates": [],
            "momentum_risk": "MEDIUM"
        }
    except Exception as e:
        return {
            "strength": "MEDIUM",
            "reason": f"API 오류: {str(e)[:30]}",
            "repeat_count": 0,
            "best_match_dates": [],
            "momentum_risk": "MEDIUM"
        }


def run_step_c_individual(
    stock_name: str,
    title: str,
    body: str = "",
    step_a_result: Optional[dict] = None,
    project_id: str = PROJECT_ID,
) -> dict:
    """
    경로 1: 개별 종목 기사 분석.

    Args:
        stock_name: 종목명
        title: 현재 기사 제목
        body: 현재 기사 본문
        step_a_result: Step A 결과 (material_type 참고)
        project_id: GCP 프로젝트 ID

    Returns:
        {
            "article_type": "individual",
            "stock_name": str,
            "past_cases_count": int,
            "past_cases": list,       # 최대 10개
            "strength": dict,          # Claude 강도 판단
            "stats": dict,             # D1~D5 수익률 통계 (과거 사례 전체)
            "stats_with_data": dict,   # D1~D5 통계 (rise_rate 있는 것만)
        }
    """
    bq_client = bigquery.Client(project=project_id)
    past_cases = fetch_stock_cases(stock_name, bq_client)

    # rise_rate 데이터 있는 사례만 통계용으로 분리
    cases_with_data = [c for c in past_cases if c.get("rise_rate") is not None]

    # Claude 강도 판단
    material_type = step_a_result.get("material_type") if step_a_result else None
    strength = assess_strength_with_claude(
        stock_name, title, body, past_cases, material_type
    )

    return {
        "article_type": "individual",
        "stock_name": stock_name,
        "past_cases_count": len(past_cases),
        "past_cases": past_cases[:10],  # 출력용 최대 10개
        "strength": strength,
        "stats": aggregate_dn_stats(past_cases),
        "stats_with_data": aggregate_dn_stats(cases_with_data),
    }


# ============================================================================
# 경로 2: 테마 기사
# ============================================================================

def run_step_c_theme(
    similar_cases: list[dict],
    strong_threshold: float = STRONG_STOCK_THRESHOLD,
    leader_threshold: float = LEADER_STOCK_THRESHOLD,
) -> dict:
    """
    경로 2: 테마 기사 분석.
    Step B의 similar_cases를 받아서 강한 종목 필터링 + 통계 산출.

    Args:
        similar_cases: Step B 결과 (core_theme/all_themes 매칭 과거 사례들)
        strong_threshold: D0 등락률 필터 기준 (기본 3%)
        leader_threshold: 대장 종목 기준 (기본 7%)

    Returns:
        {
            "article_type": "theme",
            "total_cases": int,         # 전체 유사 사례 수
            "with_data": int,           # rise_rate 채워진 사례 수
            "theme_dates": list,        # 유사 테마 날짜 목록 (unique)
            "strong_cases": list,       # D0 강한 종목 사례들
            "leader_cases": list,       # D0 대장 종목 사례들
            "top_by_d1": list,          # D+1 평균 수익 TOP5 종목
            "top_by_d5": list,          # D+5 평균 수익 TOP5 종목
            "top_by_freq": list,        # 빈도 TOP5 종목 (=자주 강했던 종목)
            "all_stats": dict,          # 전체 강한 종목의 D1~D5 통계
        }
    """
    # 1. rise_rate가 채워진 사례 필터
    cases_with_data = [c for c in similar_cases if c.get("rise_rate") is not None]

    # 2. 강한 종목 / 대장 종목 필터
    strong_cases = [
        c for c in cases_with_data
        if safe_float(c.get("rise_rate")) is not None
        and safe_float(c.get("rise_rate")) >= strong_threshold
    ]
    leader_cases = [
        c for c in cases_with_data
        if safe_float(c.get("rise_rate")) is not None
        and safe_float(c.get("rise_rate")) >= leader_threshold
    ]

    # 3. 유사 테마 날짜 목록 (unique, 최신순)
    theme_dates = sorted(
        list(set(str(c.get("event_date", ""))[:10] for c in similar_cases
                 if c.get("event_date"))),
        reverse=True
    )

    # 4. 종목별 집계 (strong 기준)
    stock_map: dict[str, list[dict]] = {}
    for c in strong_cases:
        name = c.get("stock_name", "")
        if name:
            stock_map.setdefault(name, []).append(c)

    # 5. 종목별 D+1~D+5 평균 수익 계산
    stock_summaries = []
    for stock_name, cases in stock_map.items():
        d1_vals = [safe_float(c.get("d1_return")) for c in cases]
        d5_vals = [safe_float(c.get("d5_return")) for c in cases]
        avg_rise = statistics.mean(
            [safe_float(c.get("rise_rate")) for c in cases
             if safe_float(c.get("rise_rate")) is not None]
        ) if cases else 0
        stock_summaries.append({
            "stock_name": stock_name,
            "freq": len(cases),                          # 빈도 (강한 날 수)
            "avg_rise": round(avg_rise, 2),              # D0 평균 등락률
            "d1_avg": compute_stats(d1_vals)["avg"],
            "d5_avg": compute_stats(d5_vals)["avg"],
            "d1_win_rate": compute_stats(d1_vals)["win_rate"],
            "d5_win_rate": compute_stats(d5_vals)["win_rate"],
            "cases": cases[:5],                          # 참고용 사례 최대 5개
        })

    # 6. 랭킹 (데이터 없는 종목 제외)
    summaries_with_d1 = [s for s in stock_summaries if s["d1_avg"] is not None]
    summaries_with_d5 = [s for s in stock_summaries if s["d5_avg"] is not None]

    top_by_d1 = sorted(summaries_with_d1, key=lambda x: x["d1_avg"], reverse=True)[:5]
    top_by_d5 = sorted(summaries_with_d5, key=lambda x: x["d5_avg"], reverse=True)[:5]
    top_by_freq = sorted(stock_summaries, key=lambda x: x["freq"], reverse=True)[:5]

    # 7. 전체 강한 종목 통계
    all_stats = aggregate_dn_stats(strong_cases)

    return {
        "article_type": "theme",
        "total_cases": len(similar_cases),
        "with_data": len(cases_with_data),
        "strong_count": len(strong_cases),
        "leader_count": len(leader_cases),
        "theme_dates": theme_dates[:20],        # 최대 20개 날짜
        "strong_cases": strong_cases[:20],      # 참고용 최대 20개
        "leader_cases": leader_cases[:10],      # 참고용 최대 10개
        "top_by_d1": top_by_d1,
        "top_by_d5": top_by_d5,
        "top_by_freq": top_by_freq,
        "all_stats": all_stats,
    }


# ============================================================================
# 테스트
# ============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("Step C 유사 사례 분석 테스트")
    print("=" * 70)

    # 테스트 모드 선택
    mode = sys.argv[1] if len(sys.argv) > 1 else "theme"

    if mode == "individual":
        print("\n[경로 1] 개별 종목 기사 분석")
        result = run_step_c_individual(
            stock_name="이수페타시스",
            title="군용 통신장비 수출 계약 1,200억 체결",
            body="방위산업 수출 계약을 통한 대규모 수주...",
            step_a_result={"verdict": "PASS", "material_type": "수주/계약"},
        )
        print(f"  종목: {result['stock_name']}")
        print(f"  과거 사례: {result['past_cases_count']}건")
        print(f"  강도: {result['strength'].get('strength')} — {result['strength'].get('reason')}")
        d1_stat = result['stats_with_data']['d1']
        print(f"  D+1 통계 ({d1_stat['count']}건): "
              f"avg={d1_stat['avg']}% / 승률={d1_stat['win_rate']}%")

    elif mode == "theme":
        print("\n[경로 2] 테마 기사 분석 (더미 데이터)")
        dummy_cases = [
            {"stock_name": "이수페타시스", "event_date": "2026-01-15",
             "rise_rate": 8.5, "d1_return": 3.2, "d5_return": -1.1},
            {"stock_name": "이수페타시스", "event_date": "2025-11-20",
             "rise_rate": 12.1, "d1_return": -0.5, "d5_return": 4.2},
            {"stock_name": "한화에어로", "event_date": "2026-01-15",
             "rise_rate": 5.3, "d1_return": 2.1, "d5_return": 7.8},
            {"stock_name": "한화에어로", "event_date": "2025-11-20",
             "rise_rate": 4.1, "d1_return": 1.8, "d5_return": 3.5},
            {"stock_name": "LIG넥스원", "event_date": "2026-01-15",
             "rise_rate": 9.8, "d1_return": 5.5, "d5_return": 2.3},
            {"stock_name": "세진티에스", "event_date": "2025-08-10",
             "rise_rate": 1.2, "d1_return": -2.1, "d5_return": -3.5},  # 약한 종목 (필터 제외)
        ]
        result = run_step_c_theme(dummy_cases)
        print(f"  전체 유사 사례: {result['total_cases']}건")
        print(f"  강한 종목 사례 (D0>3%): {result['strong_count']}건")
        print(f"  대장 종목 사례 (D0>7%): {result['leader_count']}건")
        print(f"\n  D+1 수익 TOP 종목:")
        for s in result['top_by_d1']:
            print(f"    {s['stock_name']}: D+1 avg={s['d1_avg']}% / "
                  f"D+5 avg={s['d5_avg']}% / 빈도={s['freq']}회")
        d1_all = result['all_stats']['d1']
        print(f"\n  전체 강한 종목 D+1 통계: avg={d1_all['avg']}% "
              f"/ 승률={d1_all['win_rate']}%")

    print("\n✅ Step C 완료")
