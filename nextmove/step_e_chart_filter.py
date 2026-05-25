"""
Step E: 차트 통과 필터

역할: 종목이 현재 편입 가능한 차트 위치에 있는지 확인
- 종가 위치: 8MA/20MA 위 + 20일 고가 대비 N% 이상
- 거래대금: 절대 기준 + 평균 대비 배율 기준

입력:  stock_code, date (기본: 오늘)
출력:  {"verdict": "PASS|FLAG|FAIL", "reason": str, 세부 지표...}
"""

import sys
import io
from datetime import datetime, timedelta
from typing import Optional

# (removed: sys.stdout reassign)

# ============================================================================
# 기준값 설정
# ============================================================================

# 종가 위치 기준
MA_SHORT = 8        # 단기 이동평균
MA_MID = 20         # 중기 이동평균
MA_LONG = 60        # 장기 이동평균
HIGH_N = 20         # N일 고가 대비 위치 계산
HIGH_THRESHOLD = 0.75  # 20일 고가의 75% 이상

# 거래대금 기준 (단위: 억)
MIN_VOLUME_PASS = 30       # 최소 거래대금 (PASS 기준)
MIN_VOLUME_FLAG = 10       # 최소 거래대금 (FLAG 기준)
AVG_VOLUME_RATIO = 1.0     # 평균 대비 배율 (1.0 = 평균 이상)


# ============================================================================
# pykrx 데이터 조회
# ============================================================================

def get_ohlcv(stock_code: str, n_days: int = 80) -> Optional[object]:
    """
    pykrx로 최근 N일 OHLCV 조회.

    Args:
        stock_code: 6자리 종목코드 (e.g., "005930")
        n_days:     조회할 영업일 수 (MA 계산용 버퍼 포함)

    Returns:
        pandas DataFrame (날짜 인덱스, columns: 시가/고가/저가/종가/거래량/거래대금)
        or None (조회 실패)
    """
    try:
        from pykrx import stock
        end = datetime.today().strftime("%Y%m%d")
        # n_days보다 여유 있게 달력일 기준으로 시작일 설정 (영업일 확보)
        start = (datetime.today() - timedelta(days=n_days * 2)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv_by_date(start, end, stock_code)
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        print(f"  ⚠️  pykrx 조회 실패 ({stock_code}): {e}")
        return None


def calc_chart_metrics(df) -> Optional[dict]:
    """
    DataFrame → 차트 지표 계산.

    Returns:
        {
            "close": float,           # 최근 종가
            "ma8": float,
            "ma20": float,
            "ma60": float,
            "high20": float,          # 20일 고가
            "volume_today": float,    # 당일 거래대금 (억)
            "volume_avg20": float,    # 20일 평균 거래대금 (억)
            "data_days": int,         # 유효 데이터 수
        }
    """
    if df is None or len(df) < MA_SHORT:
        return None

    # 컬럼명 정규화 (pykrx 버전별 차이 대응)
    # 컬럼명 탐색 (pykrx: '시가','고가','저가','종가','거래량','등락률')
    col_map = {}
    for col in df.columns:
        if col == '종가' or '종가' in col:
            col_map['close'] = col
        elif col == '고가' or '고가' in col:
            col_map['high'] = col
        elif col == '거래량' or '거래량' in col:
            col_map['volume'] = col
        elif col == '거래대금' or '대금' in col:
            col_map['amount'] = col  # 있으면 직접 사용

    if 'close' not in col_map:
        return None

    close_col = col_map['close']
    high_col = col_map.get('high', None)
    vol_col = col_map.get('volume', None)
    amount_col = col_map.get('amount', None)

    recent = df.tail(MA_LONG)  # 최근 60일 기준
    closes = recent[close_col]

    close = float(closes.iloc[-1])
    ma8 = float(closes.tail(MA_SHORT).mean()) if len(closes) >= MA_SHORT else None
    ma20 = float(closes.tail(MA_MID).mean()) if len(closes) >= MA_MID else None
    ma60 = float(closes.tail(MA_LONG).mean()) if len(closes) >= MA_LONG else None

    high20 = float(recent[high_col].tail(HIGH_N).max()) if high_col and len(recent) >= HIGH_N else None

    vol_today = None
    vol_avg20 = None

    if amount_col:
        # 거래대금 직접 사용 (신버전 pykrx)
        amounts = recent[amount_col].tail(MA_MID)
        if len(amounts) >= 1:
            vol_today = float(amounts.iloc[-1]) / 1e8
        if len(amounts) >= MA_MID:
            vol_avg20 = float(amounts.mean()) / 1e8
    elif vol_col:
        # 거래대금 = 거래량 × 종가 근사 계산 (pykrx가 거래대금 미제공 시)
        vols = recent[vol_col].tail(MA_MID)
        cls = closes.tail(MA_MID)
        if len(vols) >= 1:
            vol_today = float(vols.iloc[-1]) * float(cls.iloc[-1]) / 1e8
        if len(vols) >= MA_MID:
            vol_avg20 = float((vols * cls).mean()) / 1e8

    return {
        "close": close,
        "ma8": ma8,
        "ma20": ma20,
        "ma60": ma60,
        "high20": high20,
        "volume_today": vol_today,
        "volume_avg20": vol_avg20,
        "data_days": len(df),
    }


# ============================================================================
# 필터 판정
# ============================================================================

def evaluate(metrics: dict) -> dict:
    """
    차트 지표 → PASS / FLAG / FAIL 판정.

    채점 방식 (점수 합산):
      +2: 종가 > 8MA
      +2: 종가 > 20MA
      +1: 종가 >= 20일고가 * HIGH_THRESHOLD
      +2: 거래대금 >= MIN_VOLUME_PASS
      +1: 거래대금 >= 평균 * AVG_VOLUME_RATIO

    PASS: 6점 이상 (5점 만점 중 — 최대 8점)
    FLAG: 4~5점
    FAIL: 3점 이하 또는 거래대금 < MIN_VOLUME_FLAG
    """
    score = 0
    checks = {}

    close = metrics.get("close", 0)

    # 1. 종가 vs 8MA
    ma8 = metrics.get("ma8")
    if ma8 is not None:
        above_ma8 = close >= ma8
        checks["ma8_above"] = above_ma8
        if above_ma8:
            score += 2
    else:
        checks["ma8_above"] = None

    # 2. 종가 vs 20MA
    ma20 = metrics.get("ma20")
    if ma20 is not None:
        above_ma20 = close >= ma20
        checks["ma20_above"] = above_ma20
        if above_ma20:
            score += 2
    else:
        checks["ma20_above"] = None

    # 3. 종가 vs 20일 고가
    high20 = metrics.get("high20")
    if high20 is not None and high20 > 0:
        high_pct = close / high20
        checks["high20_pct"] = round(high_pct * 100, 1)
        if high_pct >= HIGH_THRESHOLD:
            score += 1
    else:
        checks["high20_pct"] = None

    # 4. 거래대금 절대 기준
    vol = metrics.get("volume_today")
    if vol is not None:
        checks["volume_today"] = round(vol, 1)
        if vol < MIN_VOLUME_FLAG:
            # 거래대금 너무 적으면 강제 FAIL
            return {
                "verdict": "FAIL",
                "reason": f"거래대금 부족 ({vol:.0f}억 < {MIN_VOLUME_FLAG}억)",
                "score": 0,
                **checks,
                **{k: metrics[k] for k in ["close", "ma8", "ma20", "ma60", "volume_avg20"] if k in metrics}
            }
        if vol >= MIN_VOLUME_PASS:
            score += 2
    else:
        checks["volume_today"] = None

    # 5. 거래대금 vs 평균
    vol_avg = metrics.get("volume_avg20")
    if vol is not None and vol_avg is not None and vol_avg > 0:
        vol_ratio = vol / vol_avg
        checks["volume_ratio"] = round(vol_ratio, 2)
        if vol_ratio >= AVG_VOLUME_RATIO:
            score += 1
    else:
        checks["volume_ratio"] = None

    # 판정
    if score >= 6:
        verdict = "PASS"
        reason = _build_reason(checks, metrics, "통과")
    elif score >= 4:
        verdict = "FLAG"
        reason = _build_reason(checks, metrics, "부분충족")
    else:
        verdict = "FAIL"
        reason = _build_reason(checks, metrics, "미달")

    return {
        "verdict": verdict,
        "reason": reason,
        "score": score,
        **checks,
        "close": metrics.get("close"),
        "ma8": metrics.get("ma8"),
        "ma20": metrics.get("ma20"),
        "ma60": metrics.get("ma60"),
        "volume_avg20": metrics.get("volume_avg20"),
    }


def _build_reason(checks: dict, metrics: dict, label: str) -> str:
    parts = []
    if checks.get("ma8_above") is True:
        parts.append("8MA↑")
    elif checks.get("ma8_above") is False:
        parts.append("8MA↓")
    if checks.get("ma20_above") is True:
        parts.append("20MA↑")
    elif checks.get("ma20_above") is False:
        parts.append("20MA↓")
    if checks.get("high20_pct") is not None:
        parts.append(f"고가대비{checks['high20_pct']}%")
    vol = checks.get("volume_today")
    if vol is not None:
        parts.append(f"대금{vol:.0f}억")
    return f"{label}: " + " | ".join(parts) if parts else label


# ============================================================================
# 통합 실행
# ============================================================================

def run_step_e(
    stock_code: str,
    stock_name: str = "",
    date: Optional[str] = None,
) -> dict:
    """
    Step E 전체 실행.

    Args:
        stock_code: 6자리 종목코드
        stock_name: 종목명 (로그용)
        date:       기준일 (YYYYMMDD, 기본 오늘)

    Returns:
        {
            "stock_code": str,
            "stock_name": str,
            "verdict": "PASS|FLAG|FAIL",
            "reason": str,
            "score": int,
            "ma8_above": bool,
            "ma20_above": bool,
            "high20_pct": float,
            "volume_today": float,
            "volume_ratio": float,
            "close": float,
            "ma8": float,
            "ma20": float,
            "ma60": float,
            "volume_avg20": float,
        }
    """
    base = {"stock_code": stock_code, "stock_name": stock_name}

    df = get_ohlcv(stock_code)
    if df is None:
        return {**base, "verdict": "FAIL", "reason": "pykrx 데이터 없음", "score": 0}

    metrics = calc_chart_metrics(df)
    if metrics is None:
        return {**base, "verdict": "FAIL", "reason": "데이터 부족 (계산 불가)", "score": 0}

    result = evaluate(metrics)
    return {**base, **result}


def run_step_e_batch(
    candidates: list[dict],
    min_verdict: str = "FLAG",
) -> list[dict]:
    """
    여러 종목을 한 번에 필터링.

    Args:
        candidates:   [{"stock_code": "...", "stock_name": "..."}, ...]
        min_verdict:  최소 통과 기준 ("PASS" or "FLAG")

    Returns:
        통과 종목만 포함한 리스트 (verdict 추가됨)
    """
    allowed = {"PASS"} if min_verdict == "PASS" else {"PASS", "FLAG"}
    results = []
    for cand in candidates:
        r = run_step_e(
            stock_code=cand.get("stock_code", ""),
            stock_name=cand.get("stock_name", ""),
        )
        print(f"  [{r['verdict']}] {r.get('stock_name','?')} ({r.get('stock_code','?')}) — {r['reason']}")
        if r["verdict"] in allowed:
            results.append(r)
    return results


# ============================================================================
# 테스트
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Step E 차트 통과 필터 테스트")
    print("=" * 70)

    test_cases = [
        {"stock_code": "086520", "stock_name": "에코프로"},
        {"stock_code": "005930", "stock_name": "삼성전자"},
        {"stock_code": "000660", "stock_name": "SK하이닉스"},
        {"stock_code": "373220", "stock_name": "LG에너지솔루션"},
    ]

    for case in test_cases:
        print(f"\n[{case['stock_name']}]")
        result = run_step_e(**case)
        verdict_emoji = {"PASS": "✅", "FLAG": "🟡", "FAIL": "❌"}.get(result["verdict"], "?")
        print(f"  판정: {result['verdict']} {verdict_emoji} (점수: {result.get('score', 0)}/8)")
        print(f"  이유: {result['reason']}")
        if result.get("close"):
            print(f"  종가: {result['close']:,.0f}  MA8: {result.get('ma8', 'N/A'):,.0f}  MA20: {result.get('ma20', 'N/A'):,.0f}")
        if result.get("volume_today"):
            print(f"  거래대금: {result.get('volume_today', 0):.0f}억  (평균대비 {result.get('volume_ratio', 0):.1f}x)")
        if result.get("high20_pct"):
            print(f"  20일고가 대비: {result.get('high20_pct', 0):.1f}%")

    print("\n" + "=" * 70)
    print("배치 필터 테스트")
    print("=" * 70)
    filtered = run_step_e_batch(test_cases, min_verdict="PASS")
    print(f"\n통과 종목: {len(filtered)}/{len(test_cases)}개")
    for r in filtered:
        print(f"  → {r['stock_name']} ({r['stock_code']})")
