"""
test_pipeline.py: NextMove 파이프라인 통합 테스트

사용자 귀환 후 ANTHROPIC_API_KEY 설정 완료 시 이 스크립트로 빠른 검증.

실행:
  python3 nextmove/test_pipeline.py          # 전체 테스트
  python3 nextmove/test_pipeline.py --mock   # Claude API 없이 모의 테스트
  python3 nextmove/test_pipeline.py --env    # 환경 변수 확인만
"""

from __future__ import annotations

import os
import sys


# ============================================================================
# 환경 변수 체크
# ============================================================================

def check_env() -> dict:
    results = {}
    results["ANTHROPIC_API_KEY"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    results["KRX_AUTH_KEY"] = bool(os.environ.get("KRX_AUTH_KEY"))

    # BigQuery ADC 체크
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project="infin-stock-bot")
        client.query("SELECT 1").result()
        results["BigQuery_ADC"] = True
    except Exception as e:
        results["BigQuery_ADC"] = False
        results["BigQuery_error"] = str(e)[:60]

    return results


def print_env_report(env: dict) -> None:
    print("\n[환경 변수 체크]")
    icons = {True: "✅", False: "❌"}
    for key, val in env.items():
        if key.endswith("_error"):
            continue
        icon = icons.get(val, "⚠️")
        err = env.get(f"{key}_error", "")
        err_str = f" — {err}" if err else ""
        print(f"  {icon} {key}{err_str}")

    if not env.get("ANTHROPIC_API_KEY"):
        print("""
  ⚡ ANTHROPIC_API_KEY 설정 방법:
     echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
     source ~/.bashrc
  """)


# ============================================================================
# Step A 테스트
# ============================================================================

def test_step_a(mock: bool = False) -> bool:
    print("\n[Step A] 탈락 필터 테스트")
    from step_a_filter import keyword_filter

    # 1차 키워드 필터 (API 불필요)
    result = keyword_filter("테스트", "유상증자 발표")
    ok = result is not None and result.get("verdict") == "REJECT"
    print(f"  1차 필터 (유상증자 REJECT): {'✅' if ok else '❌'}")

    result2 = keyword_filter("테스트", "1,200억 수주 확정")
    ok2 = result2 is None  # 2차로 넘어가야 함
    print(f"  1차 필터 (수주계약 통과): {'✅' if ok2 else '❌'}")

    if not mock:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("  ⚠️ ANTHROPIC_API_KEY 없음 — Claude 2차 테스트 건너뜀")
            return ok and ok2

        from step_a_filter import claude_filter
        try:
            result3 = claude_filter("테스트사", "2차전지 사업 진출 검토", "")
            ok3 = result3.get("verdict") in ("REJECT", "FLAG")
            print(f"  2차 Claude ('검토' → REJECT/FLAG): {'✅' if ok3 else '❌'} → {result3.get('verdict')}")
        except Exception as e:
            print(f"  ❌ Claude API 오류: {e}")
            return False

    return ok and ok2


# ============================================================================
# Step B 테스트
# ============================================================================

def test_step_b() -> bool:
    print("\n[Step B] 테마 슬라이싱 테스트")
    from step_b_theme_slicing import extract_themes, clean_core_theme

    # 1차 테마 추출 (BigQuery 불필요)
    themes = extract_themes("유리기판10-9, 반도체3, 로봇")
    ok = themes == ["유리기판", "반도체", "로봇"]
    print(f"  테마 추출 검증: {'✅' if ok else '❌'} → {themes}")

    core = clean_core_theme("방산10-5")
    ok2 = core == "방산"
    print(f"  코어테마 정규화: {'✅' if ok2 else '❌'} → {core}")

    # BigQuery 쿼리 테스트
    try:
        from step_b_theme_slicing import search_similar_cases
        cases = search_similar_cases("방산", ["방산", "K방산"], limit=5)
        print(f"  BQ 테마 검색 ('방산'): {'✅' if isinstance(cases, list) else '❌'} → {len(cases)}건")
    except Exception as e:
        print(f"  ❌ BQ 쿼리 오류: {e}")
        return False

    return ok and ok2


# ============================================================================
# Step C 테스트 (개별 종목)
# ============================================================================

def test_step_c_individual(mock: bool = False) -> bool:
    print("\n[Step C] 개별 종목 유사 사례 분석 테스트")
    from step_c_similarity import fetch_stock_cases
    from google.cloud import bigquery

    try:
        client = bigquery.Client(project="infin-stock-bot")
        cases = fetch_stock_cases("이수페타시스", client)
        print(f"  BQ 종목 조회 ('이수페타시스'): {'✅' if isinstance(cases, list) else '❌'} → {len(cases)}건")
        if cases:
            sample = cases[0]
            rise = sample.get("rise_rate")
            print(f"    샘플: {str(sample.get('event_date',''))[:10]} / rise_rate={rise}")
    except Exception as e:
        print(f"  ❌ BQ 조회 오류: {e}")
        return False

    if not mock and not os.environ.get("ANTHROPIC_API_KEY"):
        print("  ⚠️ ANTHROPIC_API_KEY 없음 — Claude 강도 판단 테스트 건너뜀")

    return True


# ============================================================================
# Step C 테스트 (테마)
# ============================================================================

def test_step_c_theme() -> bool:
    print("\n[Step C] 테마 분석 테스트 (더미 데이터)")
    from step_c_similarity import run_step_c_theme

    dummy = [
        {"stock_name": "이수페타시스", "event_date": "2026-01-15",
         "rise_rate": 8.5, "d1_return": 3.2, "d5_return": -1.1},
        {"stock_name": "한화에어로", "event_date": "2026-01-15",
         "rise_rate": 5.3, "d1_return": 2.1, "d5_return": 7.8},
        {"stock_name": "세진티에스", "event_date": "2025-08-10",
         "rise_rate": 1.2, "d1_return": -2.1, "d5_return": -3.5},  # 필터 대상
    ]
    result = run_step_c_theme(dummy, strong_threshold=3.0)
    ok = result["strong_count"] == 2  # 세진티에스 제외
    print(f"  강한 종목 필터 (D0>3%): {'✅' if ok else '❌'} → {result['strong_count']}건 (예상 2)")
    return ok


# ============================================================================
# Step D 테스트
# ============================================================================

def test_step_d() -> bool:
    print("\n[Step D] 카드 출력 테스트")
    from step_d_output import format_individual_card, format_theme_card

    # 개별 종목 카드
    dummy_c = {
        "article_type": "individual",
        "stock_name": "이수페타시스",
        "past_cases_count": 42,
        "strength": {"strength": "STRONG", "reason": "수주 규모 역대 최대",
                     "repeat_count": 1, "best_match_dates": ["2026-01-15"],
                     "momentum_risk": "LOW"},
        "stats_with_data": {
            "d1": {"count": 10, "avg": 3.2, "median": 2.8, "win_rate": 70.0, "max": 12.1, "min": -4.5},
            "d3": {"count": 10, "avg": 1.8, "median": 1.2, "win_rate": 60.0, "max": 8.5, "min": -3.2},
            "d5": {"count": 10, "avg": 1.2, "median": 0.9, "win_rate": 55.0, "max": 9.8, "min": -4.8},
        },
        "stats": {},
    }
    card = format_individual_card(dummy_c, {"verdict": "PASS", "material_type": "수주/계약"})
    ok = "이수페타시스" in card and "STRONG" in card
    print(f"  개별 종목 카드 생성: {'✅' if ok else '❌'}")
    print(card)
    return ok


# ============================================================================
# 통합 실행
# ============================================================================

def main() -> None:
    mock = "--mock" in sys.argv
    env_only = "--env" in sys.argv

    print("=" * 65)
    print("NextMove 파이프라인 통합 테스트")
    print(f"모드: {'환경 확인만' if env_only else '모의 실행' if mock else '실제 실행'}")
    print("=" * 65)

    # 환경 확인
    env = check_env()
    print_env_report(env)
    if env_only:
        return

    if not env.get("BigQuery_ADC"):
        print("\n❌ BigQuery 연결 실패 — 테스트 중단")
        print("   gcloud auth application-default login 실행 필요")
        sys.exit(1)

    # 각 Step 테스트
    results = {}
    results["Step A"] = test_step_a(mock=mock)
    results["Step B"] = test_step_b()
    results["Step C (개별)"] = test_step_c_individual(mock=mock)
    results["Step C (테마)"] = test_step_c_theme()
    results["Step D"] = test_step_d()

    # 요약
    print("\n" + "=" * 65)
    print("테스트 결과 요약")
    print("=" * 65)
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for step, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {step}")
    print(f"\n  결과: {passed}/{total} 통과")

    if passed == total:
        print("\n🚀 모든 테스트 통과! 실제 기사 입력 준비 완료.")
        print("   python3 nextmove/run_pipeline.py individual --stock '종목명' --title '기사제목'")
    else:
        print("\n⚠️ 일부 테스트 실패. 위 항목 확인 후 재실행.")
    print("=" * 65)


if __name__ == "__main__":
    main()
