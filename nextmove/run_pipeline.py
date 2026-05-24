"""
NextMove 메인 파이프라인

사용법:
  # 개별 종목 기사 분석
  python nextmove/run_pipeline.py individual \
    --stock "이수페타시스" \
    --title "군용 통신장비 수출 계약 1,200억 체결" \
    --body "방위산업 수출 계약..."

  # 테마 기사 분석
  python nextmove/run_pipeline.py theme \
    --core-theme "방산" \
    --themes "방산,수출,K방산,국방" \
    --title "트럼프 2기 방산 예산 증액 발표"

  # 파이프라인 플로우
  개별: Article → [A: 필터] → [C: 개별유사분석] → [D: 카드출력]
  테마: Article → [A: 필터] → [B: 테마슬라이싱] → [C: 테마분석] → [D: 카드출력]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from step_a_filter import run_step_a
from step_b_theme_slicing import run_step_b
from step_c_similarity import run_step_c_individual, run_step_c_theme
from step_d_output import run_step_d


# ============================================================================
# 경로 1: 개별 종목 기사 파이프라인
# ============================================================================

def pipeline_individual(
    stock_name: str,
    title: str,
    body: str = "",
    project_id: str = "infin-stock-bot",
    skip_filter: bool = False,
    json_output: bool = False,
) -> dict:
    """
    개별 종목 기사 분석 파이프라인.

    Flow: Step A → Step C(개별) → Step D

    Args:
        stock_name: 종목명
        title: 기사 제목
        body: 기사 본문 (선택)
        project_id: GCP 프로젝트
        skip_filter: True면 Step A 건너뜀
        json_output: True면 카드 대신 JSON 출력

    Returns:
        결과 dict
    """
    print(f"\n{'='*65}")
    print(f"[NextMove] 개별 종목 분석: {stock_name}")
    print(f"  기사: {title[:60]}{'...' if len(title)>60 else ''}")
    print(f"{'='*65}")

    step_a_result = None

    # ── Step A: 재료 필터 ──────────────────────────────────────────
    if not skip_filter:
        print("\n[Step A] 재료 필터링...")
        step_a_result = run_step_a(stock_name, title, body)
        verdict = step_a_result.get("verdict", "FLAG")
        print(f"  → {verdict}  ({step_a_result.get('reason', '')})")

        if verdict == "REJECT":
            print("\n⛔ REJECT: 단기 모멘텀 가능성 없음. 분석 종료.")
            result = {
                "status": "REJECTED",
                "stock_name": stock_name,
                "title": title,
                "step_a": step_a_result,
            }
            if json_output:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return result

        if verdict == "FLAG":
            print("  ⚠️ FLAG: 애매한 재료 — 마스터 판단 권고. 분석은 계속합니다.")
    else:
        print("[Step A] 건너뜀 (--skip-filter)")

    # ── Step C: 개별 유사 분석 ────────────────────────────────────
    print("\n[Step C] 유사 사례 분석 (BigQuery 조회 + Claude 강도 판단)...")
    c_result = run_step_c_individual(
        stock_name=stock_name,
        title=title,
        body=body,
        step_a_result=step_a_result,
        project_id=project_id,
    )
    print(f"  → 과거 사례 {c_result['past_cases_count']}건 조회 완료")
    strength = c_result.get("strength", {}).get("strength", "?")
    print(f"  → 재료 강도: {strength}")

    # ── Step D: 카드 출력 ─────────────────────────────────────────
    print("\n[Step D] 결과 카드 생성...")
    d_result = run_step_d(
        c_result=c_result,
        step_a_result=step_a_result,
        print_card=not json_output,
    )

    final = {
        "status": "OK",
        "pipeline": "individual",
        "stock_name": stock_name,
        "title": title,
        "step_a": step_a_result,
        "step_c": {
            "past_cases_count": c_result.get("past_cases_count"),
            "strength": c_result.get("strength"),
            "stats_with_data": c_result.get("stats_with_data"),
        },
        "card": d_result,
    }

    if json_output:
        print(json.dumps(final, ensure_ascii=False, default=str, indent=2))

    return final


# ============================================================================
# 경로 2: 테마 기사 파이프라인
# ============================================================================

def pipeline_theme(
    core_theme: str,
    themes_raw: str,
    title: str = "",
    body: str = "",
    project_id: str = "infin-stock-bot",
    skip_filter: bool = False,
    json_output: bool = False,
    strong_threshold: float = 3.0,
) -> dict:
    """
    테마 기사 분석 파이프라인.

    Flow: [Step A] → Step B → Step C(테마) → Step D

    Args:
        core_theme: 코어 테마명 (예: '방산')
        themes_raw: 쉼표 구분 전체 테마 (예: '방산,수출,K방산')
        title: 기사 제목 (Step A용, 선택)
        body: 기사 본문 (Step A용, 선택)
        project_id: GCP 프로젝트
        skip_filter: True면 Step A 건너뜀
        json_output: True면 JSON 출력
        strong_threshold: 강한 종목 D0 등락률 기준 (%)

    Returns:
        결과 dict
    """
    print(f"\n{'='*65}")
    print(f"[NextMove] 테마 분석: {core_theme}")
    if title:
        print(f"  기사: {title[:60]}{'...' if len(title)>60 else ''}")
    print(f"  테마: {themes_raw}")
    print(f"{'='*65}")

    step_a_result = None

    # ── Step A: 테마 기사 필터 (선택) ────────────────────────────
    if not skip_filter and title:
        print("\n[Step A] 테마 기사 필터링...")
        step_a_result = run_step_a("테마기사", title, body)
        verdict = step_a_result.get("verdict", "FLAG")
        print(f"  → {verdict}  ({step_a_result.get('reason', '')})")
        # 테마 기사는 REJECT여도 계속 (테마 분석은 별도 가치)
        if verdict == "REJECT":
            print("  ⚠️ 기사 재료 약하나 테마 분석은 계속합니다.")
    else:
        print("[Step A] 건너뜀")

    # ── Step B: 테마 슬라이싱 ─────────────────────────────────────
    print("\n[Step B] 유사 테마 날짜 검색 (BigQuery)...")
    b_result = run_step_b(
        stock_code="",
        core_theme_raw=core_theme,
        all_themes_raw=themes_raw,
        project_id=project_id,
        limit=200,
    )
    print(f"  → 유사 사례 {b_result['case_count']}건 조회 완료")
    print(f"  → 코어테마: {b_result['core_theme']} / 테마: {b_result['themes']}")

    if b_result['case_count'] == 0:
        print("\n⚠️ 유사 테마 사례 없음. 분석 종료.")
        return {
            "status": "NO_DATA",
            "pipeline": "theme",
            "core_theme": core_theme,
            "step_b": b_result,
        }

    # ── Step C: 테마 분석 ─────────────────────────────────────────
    print("\n[Step C] 강한 종목 필터링 + 통계 산출...")
    c_result = run_step_c_theme(
        similar_cases=b_result["similar_cases"],
        strong_threshold=strong_threshold,
    )
    print(f"  → 강한 종목 사례: {c_result['strong_count']}건 "
          f"(D0>{strong_threshold}%, 총 {c_result['with_data']}건 중)")
    print(f"  → 유사 테마 날짜: {len(c_result['theme_dates'])}일")

    # ── Step D: 카드 출력 ─────────────────────────────────────────
    print("\n[Step D] 결과 카드 생성...")
    d_result = run_step_d(
        c_result=c_result,
        step_b_result=b_result,
        print_card=not json_output,
    )

    final = {
        "status": "OK",
        "pipeline": "theme",
        "core_theme": core_theme,
        "themes": b_result["themes"],
        "title": title,
        "step_a": step_a_result,
        "step_b": {
            "case_count": b_result["case_count"],
            "core_theme": b_result["core_theme"],
            "themes": b_result["themes"],
        },
        "step_c": {
            "total_cases": c_result["total_cases"],
            "with_data": c_result["with_data"],
            "strong_count": c_result["strong_count"],
            "leader_count": c_result["leader_count"],
            "theme_dates_count": len(c_result["theme_dates"]),
            "top_by_d1": c_result.get("top_by_d1"),
            "top_by_d5": c_result.get("top_by_d5"),
        },
        "card": d_result,
    }

    if json_output:
        print(json.dumps(final, ensure_ascii=False, default=str, indent=2))

    return final


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NextMove 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 개별 종목
  python nextmove/run_pipeline.py individual \\
    --stock "이수페타시스" \\
    --title "군용 통신장비 수출 계약 1,200억 체결"

  # 테마
  python nextmove/run_pipeline.py theme \\
    --core-theme "방산" \\
    --themes "방산,수출,K방산" \\
    --title "트럼프 2기 방산 예산 증액 발표"

  # JSON 출력 (자동화/로깅용)
  python nextmove/run_pipeline.py individual \\
    --stock "이수페타시스" \\
    --title "..." \\
    --json
        """
    )

    sub = parser.add_subparsers(dest="mode", required=True)

    # 개별 종목 서브커맨드
    p_ind = sub.add_parser("individual", aliases=["ind", "i"], help="개별 종목 기사 분석")
    p_ind.add_argument("--stock", required=True, help="종목명")
    p_ind.add_argument("--title", required=True, help="기사 제목")
    p_ind.add_argument("--body", default="", help="기사 본문 (선택)")
    p_ind.add_argument("--skip-filter", action="store_true", help="Step A 건너뜀")
    p_ind.add_argument("--json", action="store_true", help="JSON 출력")
    p_ind.add_argument("--project", default="infin-stock-bot")

    # 테마 서브커맨드
    p_thm = sub.add_parser("theme", aliases=["th", "t"], help="테마 기사 분석")
    p_thm.add_argument("--core-theme", required=True, help="코어 테마 (예: 방산)")
    p_thm.add_argument("--themes", required=True, help="전체 테마 쉼표 구분 (예: 방산,수출,K방산)")
    p_thm.add_argument("--title", default="", help="기사 제목 (Step A 필터용, 선택)")
    p_thm.add_argument("--body", default="", help="기사 본문 (선택)")
    p_thm.add_argument("--skip-filter", action="store_true", help="Step A 건너뜀")
    p_thm.add_argument("--strong-threshold", type=float, default=3.0,
                       help="강한 종목 D0 등락률 기준 %% (기본 3.0)")
    p_thm.add_argument("--json", action="store_true", help="JSON 출력")
    p_thm.add_argument("--project", default="infin-stock-bot")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    mode = args.mode.lower()

    if mode in ("individual", "ind", "i"):
        pipeline_individual(
            stock_name=args.stock,
            title=args.title,
            body=args.body,
            project_id=args.project,
            skip_filter=args.skip_filter,
            json_output=args.json,
        )

    elif mode in ("theme", "th", "t"):
        pipeline_theme(
            core_theme=args.core_theme,
            themes_raw=args.themes,
            title=args.title,
            body=args.body,
            project_id=args.project,
            skip_filter=args.skip_filter,
            json_output=getattr(args, "json", False),
            strong_threshold=args.strong_threshold,
        )

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
