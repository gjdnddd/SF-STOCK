"""
Step D: 종목 카드 출력 포매터

역할: Step C 결과를 사람이 읽기 쉬운 카드 형식으로 변환

경로 1 (개별 종목):
  ┌─ 종목카드 ──────────────────────────────────────
  │ 🏷 이수페타시스  [STRONG] 군용통신장비 수주/계약
  │ 📊 과거 42건 | D+1 avg +3.2% (승률 68%) | D+5 avg +1.8%
  │ ⚠️ 모멘텀 소진 위험: LOW
  │ 📅 유사 사례: 2026-01-15, 2025-11-20, 2025-08-10
  └──────────────────────────────────────────────────

경로 2 (테마):
  ┌─ 테마 분석 ─────────────────────────────────────
  │ 📡 방산/수출 테마  |  유사 날짜 8일  |  강한 종목 23개
  │
  │ 🥇 D+1 기대 수익 TOP 5
  │   1. 이수페타시스  +4.2%  (승률 75%, 4회)
  │   2. LIG넥스원     +3.5%  (승률 67%, 3회)
  │   ...
  │
  │ 📈 D+5 누적 수익 TOP 5
  │   1. 한화에어로    +8.1%  (승률 80%, 5회)
  │   ...
  │
  │ 📊 전체 강한 종목 통계
  │   D+1: avg +2.3% / 승률 62% / 23건
  │   D+5: avg +1.1% / 승률 55%
  └──────────────────────────────────────────────────

출력 형식:
  - 텍스트 카드 (콘솔 출력)
  - dict (파이프라인 연결용)
"""

from __future__ import annotations

from typing import Optional


# ============================================================================
# 공통 유틸
# ============================================================================

def _pct(val: Optional[float], default: str = "N/A") -> str:
    """float → '+1.23%' 형식."""
    if val is None:
        return default
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def _stat_line(label: str, stat: dict) -> str:
    """D+N 통계 한 줄 포매팅."""
    if stat.get("count", 0) == 0:
        return f"  {label}: 데이터 없음"
    avg = _pct(stat.get("avg"))
    wr = stat.get("win_rate")
    wr_str = f"승률{wr:.0f}%" if wr is not None else ""
    cnt = stat.get("count", 0)
    return f"  {label}: avg {avg}  {wr_str}  ({cnt}건)"


def _bar(val: Optional[float], scale: float = 10.0) -> str:
    """숫자를 시각적 바로 변환 (±10% 기준)."""
    if val is None:
        return "──"
    clamped = max(-scale, min(scale, val))
    filled = int(abs(clamped) / scale * 5)
    if val >= 0:
        return "▓" * filled + "░" * (5 - filled)
    else:
        return "░" * (5 - filled) + "▓" * filled


# ============================================================================
# 경로 1: 개별 종목 카드
# ============================================================================

STRENGTH_EMOJI = {"STRONG": "🔥", "MEDIUM": "⚖️", "WEAK": "❄️"}
RISK_EMOJI = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}


CHART_EMOJI = {"PASS": "✅", "FLAG": "🟡", "FAIL": "❌"}


def format_individual_card(
    c_result: dict,
    step_a_result: Optional[dict] = None,
    step_e_result: Optional[dict] = None,
) -> str:
    """
    개별 종목 분석 결과 → 텍스트 카드.

    Args:
        c_result: run_step_c_individual() 반환값
        step_a_result: Step A 결과 (verdict, material_type)
        step_e_result: Step E 차트 필터 결과 (선택)

    Returns:
        str: 카드 텍스트
    """
    stock_name = c_result.get("stock_name", "?")
    strength_data = c_result.get("strength", {})
    strength = strength_data.get("strength", "MEDIUM")
    reason = strength_data.get("reason", "")
    repeat = strength_data.get("repeat_count", 0)
    momentum_risk = strength_data.get("momentum_risk", "MEDIUM")
    best_dates = strength_data.get("best_match_dates", [])
    past_count = c_result.get("past_cases_count", 0)

    material_type = ""
    verdict = ""
    if step_a_result:
        material_type = step_a_result.get("material_type", "")
        verdict = step_a_result.get("verdict", "")

    stats_wd = c_result.get("stats_with_data", {})
    stats_all = c_result.get("stats", {})

    # 통계: 데이터 있는 것 우선, 없으면 전체
    d1 = stats_wd.get("d1") or stats_all.get("d1", {})
    d3 = stats_wd.get("d3") or stats_all.get("d3", {})
    d5 = stats_wd.get("d5") or stats_all.get("d5", {})

    se = STRENGTH_EMOJI.get(strength, "⚖️")
    re = RISK_EMOJI.get(momentum_risk, "🟡")

    lines = [
        "┌─ 종목 카드 " + "─" * 52,
        f"│ {se} {stock_name}  [{strength}]  {material_type}",
    ]
    if verdict:
        lines.append(f"│    Step A 판정: {verdict}")
    lines += [
        f"│    재료 평가: {reason}",
        f"│    반복 노출: {repeat}회  |  {re} 모멘텀 위험: {momentum_risk}",
        "│",
        f"│ 📊 과거 사례: {past_count}건 (수익률 데이터: {d1.get('count', 0)}건)",
        _stat_line("D+1", d1),
        _stat_line("D+3", d3),
        _stat_line("D+5", d5),
    ]
    if best_dates:
        dates_str = "  /  ".join(best_dates[:3])
        lines.append(f"│\n│ 📅 참고 사례: {dates_str}")

    # Step E 차트 필터 섹션 (있는 경우)
    if step_e_result:
        e_verdict = step_e_result.get("verdict", "?")
        e_emoji = CHART_EMOJI.get(e_verdict, "?")
        e_score = step_e_result.get("score", 0)
        e_reason = step_e_result.get("reason", "")
        lines.append("│")
        lines.append(f"│ 📈 차트 위치: {e_verdict} {e_emoji}  (점수 {e_score}/8)")
        lines.append(f"│    {e_reason}")
        if step_e_result.get("close"):
            close = step_e_result["close"]
            ma8 = step_e_result.get("ma8")
            ma20 = step_e_result.get("ma20")
            vol = step_e_result.get("volume_today")
            vol_ratio = step_e_result.get("volume_ratio")
            ma8_str = f"{ma8:,.0f}" if ma8 else "N/A"
            ma20_str = f"{ma20:,.0f}" if ma20 else "N/A"
            vol_str = f"{vol:.0f}억" if vol else "N/A"
            ratio_str = f"({vol_ratio:.1f}x)" if vol_ratio else ""
            lines.append(f"│    종가: {close:,.0f}  MA8: {ma8_str}  MA20: {ma20_str}")
            lines.append(f"│    거래대금: {vol_str} {ratio_str}")

    lines.append("└" + "─" * 63)

    return "\n".join(lines)


def format_individual_dict(c_result: dict, step_a_result: Optional[dict] = None) -> dict:
    """개별 종목 카드 → dict (파이프라인 연결용)."""
    strength_data = c_result.get("strength", {})
    stats_wd = c_result.get("stats_with_data", {})

    return {
        "type": "individual",
        "stock_name": c_result.get("stock_name"),
        "verdict": step_a_result.get("verdict") if step_a_result else None,
        "material_type": step_a_result.get("material_type") if step_a_result else None,
        "strength": strength_data.get("strength"),
        "momentum_risk": strength_data.get("momentum_risk"),
        "reason": strength_data.get("reason"),
        "past_cases_count": c_result.get("past_cases_count"),
        "d1_avg": (stats_wd.get("d1") or {}).get("avg"),
        "d1_win_rate": (stats_wd.get("d1") or {}).get("win_rate"),
        "d5_avg": (stats_wd.get("d5") or {}).get("avg"),
        "d5_win_rate": (stats_wd.get("d5") or {}).get("win_rate"),
        "best_match_dates": strength_data.get("best_match_dates", []),
    }


# ============================================================================
# 경로 2: 테마 카드
# ============================================================================

def _stock_row(i: int, s: dict, dn: str = "d1", chart_verdict: str = "") -> str:
    """종목 랭킹 한 줄 (차트 뱃지 선택)."""
    name = s.get("stock_name", "?")[:10]
    avg = _pct(s.get(f"{dn}_avg"))
    wr = s.get(f"{dn}_win_rate")
    wr_str = f"승률{wr:.0f}%" if wr is not None else "승률N/A"
    freq = s.get("freq", 0)
    bar = _bar(s.get(f"{dn}_avg"))
    badge = f"  {CHART_EMOJI.get(chart_verdict, '')}" if chart_verdict else ""
    return f"│  {i}. {name:<12} {avg:>7}  {bar}  {wr_str}  ({freq}회){badge}"


def format_theme_card(
    c_result: dict,
    core_theme: str = "",
    themes: list[str] = None,
    step_e_results: Optional[dict] = None,
) -> str:
    """
    테마 분석 결과 → 텍스트 카드.

    Args:
        c_result: run_step_c_theme() 반환값
        core_theme: 코어 테마명 (표시용)
        themes: 전체 테마 리스트 (표시용)
        step_e_results: {stock_name: step_e_result} 차트 필터 결과 (선택)

    Returns:
        str: 카드 텍스트
    """
    if themes is None:
        themes = []
    if step_e_results is None:
        step_e_results = {}

    total = c_result.get("total_cases", 0)
    with_data = c_result.get("with_data", 0)
    strong_n = c_result.get("strong_count", 0)
    leader_n = c_result.get("leader_count", 0)
    theme_dates = c_result.get("theme_dates", [])
    top_d1 = c_result.get("top_by_d1", [])
    top_d5 = c_result.get("top_by_d5", [])
    top_freq = c_result.get("top_by_freq", [])
    all_stats = c_result.get("all_stats", {})

    theme_tag = core_theme or (themes[0] if themes else "?")
    themes_str = ", ".join(themes[:5]) if themes else core_theme
    dates_str = "  ".join(theme_dates[:6])
    if len(theme_dates) > 6:
        dates_str += f"  외 {len(theme_dates)-6}일"

    d1_stat = all_stats.get("d1", {})
    d3_stat = all_stats.get("d3", {})
    d5_stat = all_stats.get("d5", {})

    lines = [
        "┌─ 테마 분석 카드 " + "─" * 47,
        f"│ 📡 [{theme_tag}]  테마: {themes_str}",
        f"│    유사 날짜: {len(theme_dates)}일  |  "
        f"강한 종목 사례: {strong_n}건 (D0>3%)  |  대장: {leader_n}건 (D0>7%)",
        f"│    데이터 보유: {with_data}/{total}건",
        f"│    참고 날짜: {dates_str}",
        "│",
    ]

    # D+1 TOP
    if top_d1:
        chart_note = "  (✅PASS 🟡FLAG ❌FAIL)" if step_e_results else ""
        lines.append(f"│ 🥇 D+1 기대 수익 TOP (강한 종목 기준){chart_note}")
        for i, s in enumerate(top_d1, 1):
            nm = s.get("stock_name", "")
            verdict = step_e_results.get(nm, {}).get("verdict", "") if step_e_results else ""
            lines.append(_stock_row(i, s, "d1", verdict))
        lines.append("│")

    # D+5 TOP
    if top_d5:
        lines.append("│ 📈 D+5 누적 수익 TOP")
        for i, s in enumerate(top_d5, 1):
            nm = s.get("stock_name", "")
            verdict = step_e_results.get(nm, {}).get("verdict", "") if step_e_results else ""
            lines.append(_stock_row(i, s, "d5", verdict))
        lines.append("│")

    # 빈도 TOP
    if top_freq:
        lines.append("│ 🔄 출현 빈도 TOP (테마 날 자주 강했던 종목)")
        for i, s in enumerate(top_freq, 1):
            freq = s.get("freq", 0)
            avg_rise = _pct(s.get("avg_rise"))
            d1_a = _pct(s.get("d1_avg"))
            name = s.get("stock_name", "?")[:10]
            nm = s.get("stock_name", "")
            verdict = step_e_results.get(nm, {}).get("verdict", "") if step_e_results else ""
            badge = f"  {CHART_EMOJI.get(verdict, '')}" if verdict else ""
            lines.append(f"│  {i}. {name:<12} {freq}회  D0 avg {avg_rise}  →  D+1 avg {d1_a}{badge}")
        lines.append("│")

    # 전체 통계
    lines += [
        "│ 📊 강한 종목 전체 통계",
        _stat_line("D+1", d1_stat),
        _stat_line("D+3", d3_stat),
        _stat_line("D+5", d5_stat),
        "└" + "─" * 63,
    ]

    return "\n".join(lines)


def format_theme_dict(c_result: dict, core_theme: str = "", themes: list[str] = None) -> dict:
    """테마 카드 → dict (파이프라인 연결용)."""
    if themes is None:
        themes = []
    d1_stat = c_result.get("all_stats", {}).get("d1", {})
    d5_stat = c_result.get("all_stats", {}).get("d5", {})

    return {
        "type": "theme",
        "core_theme": core_theme,
        "themes": themes,
        "total_cases": c_result.get("total_cases"),
        "strong_count": c_result.get("strong_count"),
        "leader_count": c_result.get("leader_count"),
        "theme_dates_count": len(c_result.get("theme_dates", [])),
        "top_by_d1": c_result.get("top_by_d1"),
        "top_by_d5": c_result.get("top_by_d5"),
        "top_by_freq": c_result.get("top_by_freq"),
        "d1_avg": d1_stat.get("avg"),
        "d1_win_rate": d1_stat.get("win_rate"),
        "d5_avg": d5_stat.get("avg"),
        "d5_win_rate": d5_stat.get("win_rate"),
    }


# ============================================================================
# 통합 실행
# ============================================================================

def run_step_d(
    c_result: dict,
    step_a_result: Optional[dict] = None,
    step_b_result: Optional[dict] = None,
    step_e_result: Optional[dict] = None,    # 개별종목용
    step_e_results: Optional[dict] = None,   # 테마용 {stock_name: result}
    print_card: bool = True,
) -> dict:
    """
    Step D 통합 실행: article_type에 따라 적절한 카드 포매터 호출.

    Args:
        c_result: Step C 결과
        step_a_result: Step A 결과 (optional, 개별종목용)
        step_b_result: Step B 결과 (optional, 테마용 core_theme/themes)
        step_e_result: Step E 차트 필터 결과 (개별종목용, optional)
        step_e_results: Step E 차트 필터 결과 dict (테마용, optional)
        print_card: True면 콘솔에 카드 출력

    Returns:
        카드 dict
    """
    article_type = c_result.get("article_type", "individual")

    if article_type == "individual":
        card_text = format_individual_card(c_result, step_a_result, step_e_result)
        card_dict = format_individual_dict(c_result, step_a_result)
    else:  # theme
        core_theme = ""
        themes = []
        if step_b_result:
            core_theme = step_b_result.get("core_theme", "")
            themes = step_b_result.get("themes", [])
        card_text = format_theme_card(c_result, core_theme, themes, step_e_results)
        card_dict = format_theme_dict(c_result, core_theme, themes)

    if print_card:
        print("\n" + card_text + "\n")

    card_dict["card_text"] = card_text
    return card_dict


# ============================================================================
# 테스트
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Step D 카드 포매터 테스트")
    print("=" * 70)

    # 개별 종목 더미 테스트
    print("\n[테스트 1] 개별 종목 카드")
    dummy_individual = {
        "article_type": "individual",
        "stock_name": "이수페타시스",
        "past_cases_count": 42,
        "strength": {
            "strength": "STRONG",
            "reason": "과거 대비 수주 규모 3배, 신규 고객사",
            "repeat_count": 2,
            "best_match_dates": ["2025-11-20", "2025-08-10", "2025-03-15"],
            "momentum_risk": "LOW",
        },
        "stats_with_data": {
            "d1": {"count": 15, "avg": 3.2, "median": 2.8, "win_rate": 73.3, "max": 12.1, "min": -4.5},
            "d3": {"count": 15, "avg": 2.1, "median": 1.9, "win_rate": 60.0, "max": 8.5, "min": -6.2},
            "d5": {"count": 15, "avg": 1.8, "median": 1.2, "win_rate": 53.3, "max": 15.3, "min": -8.1},
        },
        "stats": {},
    }
    dummy_a = {"verdict": "PASS", "material_type": "수주/계약"}
    run_step_d(dummy_individual, step_a_result=dummy_a)

    # 테마 더미 테스트
    print("[테스트 2] 테마 카드")
    dummy_theme = {
        "article_type": "theme",
        "total_cases": 87,
        "with_data": 62,
        "strong_count": 34,
        "leader_count": 12,
        "theme_dates": ["2026-01-15", "2025-11-20", "2025-08-10", "2025-03-15",
                        "2024-12-05", "2024-09-18", "2024-07-22", "2024-04-10"],
        "top_by_d1": [
            {"stock_name": "이수페타시스", "freq": 4, "avg_rise": 9.2, "d1_avg": 4.2,
             "d5_avg": 2.1, "d1_win_rate": 75.0, "d5_win_rate": 62.5},
            {"stock_name": "LIG넥스원", "freq": 3, "avg_rise": 7.8, "d1_avg": 3.5,
             "d5_avg": 5.1, "d1_win_rate": 66.7, "d5_win_rate": 66.7},
            {"stock_name": "한화에어로", "freq": 5, "avg_rise": 5.2, "d1_avg": 2.8,
             "d5_avg": 8.1, "d1_win_rate": 60.0, "d5_win_rate": 80.0},
        ],
        "top_by_d5": [
            {"stock_name": "한화에어로", "freq": 5, "avg_rise": 5.2, "d1_avg": 2.8,
             "d5_avg": 8.1, "d1_win_rate": 60.0, "d5_win_rate": 80.0},
            {"stock_name": "LIG넥스원", "freq": 3, "avg_rise": 7.8, "d1_avg": 3.5,
             "d5_avg": 5.1, "d1_win_rate": 66.7, "d5_win_rate": 66.7},
        ],
        "top_by_freq": [
            {"stock_name": "한화에어로", "freq": 5, "avg_rise": 5.2, "d1_avg": 2.8, "d5_avg": 8.1},
            {"stock_name": "이수페타시스", "freq": 4, "avg_rise": 9.2, "d1_avg": 4.2, "d5_avg": 2.1},
            {"stock_name": "LIG넥스원", "freq": 3, "avg_rise": 7.8, "d1_avg": 3.5, "d5_avg": 5.1},
        ],
        "all_stats": {
            "d1": {"count": 34, "avg": 2.3, "median": 1.8, "win_rate": 62.0, "max": 12.5, "min": -3.2},
            "d3": {"count": 34, "avg": 1.5, "median": 1.2, "win_rate": 55.0, "max": 9.8, "min": -5.1},
            "d5": {"count": 34, "avg": 1.1, "median": 0.8, "win_rate": 52.0, "max": 15.3, "min": -7.2},
        },
    }
    dummy_b = {"core_theme": "방산", "themes": ["방산", "수출", "K방산"]}
    run_step_d(dummy_theme, step_b_result=dummy_b)
