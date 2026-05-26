"""
Step A: 탈락 필터 (재료 단발성 판단)

역할: 기사가 단기 모멘텀을 이끌 수 있는지 판단
- 1차: Python 키워드 필터 (확정 제외, 비용 0)
- 2차: Claude API (애매한 경우만 호출)

입력:  stock_name, title, body (body 선택)
출력:  {"verdict": "PASS|FLAG|REJECT", "material_type": "...", "reason": "...", "one_shot_risk": bool}
"""

import anthropic
import json
import os
from typing import Optional


# ============================================================================
# 1차: Python 키워드 필터 (확정 제외)
# ============================================================================

HARD_EXCLUDE = {
    'CB발행': ['CB발행', '전환사채 발행'],
    'BW발행': ['BW발행', '신주인수권부사채 발행'],
    '유상증자': ['유상증자'],
    '자사주취득': ['자사주 취득', '자기주식 취득', '자사주취득'],
    '실적발표': ['실적발표', '영업이익 발표', '잠정실적', '분기실적'],
    '배당': ['배당 결정', '배당금 지급', '중간배당'],
}

# 예외: 이 키워드 있으면 "유상증자"도 1차 통과 → 2차 Claude 판단으로
EXCEPTION_KEYWORDS = ['제3자', '제3자배정', '증설', '생산능력', '설비투자', '공장 건설', '신규 공장']


def keyword_filter(title: str, body: str = "") -> Optional[dict]:
    """
    1차 키워드 필터: 확정 제외 항목이면 즉시 REJECT 반환.

    Args:
        title: 기사 제목
        body:  기사 본문 (선택)

    Returns:
        dict (REJECT 판정) or None (2차로 넘김)
    """
    text = (title + " " + body).lower()

    for exclude_type, keywords in HARD_EXCLUDE.items():
        for kw in keywords:
            if kw.lower() in text:
                # 예외: 제3자 유상증자는 통과
                if exclude_type == '유상증자':
                    if any(exc.lower() in text for exc in EXCEPTION_KEYWORDS):
                        continue  # 예외 적용, 2차로 넘김

                return {
                    "verdict": "REJECT",
                    "material_type": "확정제외",
                    "reason": f"확정제외: {exclude_type}",
                    "one_shot_risk": True
                }

    return None  # 1차 통과 → 2차로


# ============================================================================
# 2차: Claude Haiku API (애매한 경우)
# ============================================================================

SYSTEM_PROMPT = """당신은 한국 주식 단기 모멘텀 투자의 재료 필터입니다.
기사를 읽고 이 재료가 단기 주가 모멘텀으로 이어질 가능성이 있는지 판단하세요.

## 판단 기준

### REJECT (탈락)
다음 중 하나라도 해당하면 REJECT:
- 실제 결과 없이 "추진", "예정", "검토", "계획" 단계 발표
- MOU·의향서 체결 (구속력 없는 형태)
- 신청(승인 아님), 출원(등록 아님), 입찰(수주 아님)
- 이미 수일 전 알려진 재료를 재탕한 기사
- 단순 평가/선정/랭킹 상향 (실제 사건 아님)

### FLAG (마스터 판단 대기)
임팩트가 애매해서 마스터 판단이 필요한 경우:
- 계약 체결이나 금액·상대방 규모가 불명확
- 인수합병 발표 (시너지 판단 어려움)
- 해외 특정 분야 뉴스 → 국내 관련주 동반 상승 (테마 추종)
- 제3자 배정 유상증자 (상대방 기업이 핵심, 규모 판단 필요)
- 증설·설비투자 목적 유상증자 (최대주주 참여 여부, 테마 연관성 확인 필요)

### PASS (통과)
지속 모멘텀 가능성이 있는 재료:
- 실제 계약 체결 (금액 명시, 대형 고객사)
- 정부 정책 발표 (직접 수혜, 예산 배정 포함)
- FDA/식약처 승인·허가 획득 (신청 단계 아님)
- 대규모 수주 확정 (수주액 명시)
- 핵심 특허 등록 완료
- 매출 기여 가능한 공급 계약

## 출력 형식 (JSON만 출력, 다른 텍스트 절대 금지)
{
  "verdict": "PASS" | "FLAG" | "REJECT",
  "material_type": "정책호재" | "수주/계약" | "FDA/임상" | "해외모멘텀" | "테마동반" | "기타",
  "reason": "판단 근거 (30자 이내)",
  "one_shot_risk": true | false
}"""


def claude_filter(stock_name: str, title: str, body: str = "") -> dict:
    """
    2차 Claude Haiku 판단.

    Args:
        stock_name: 종목명
        title: 기사 제목
        body: 기사 본문 (선택)

    Returns:
        dict: {"verdict": "PASS|FLAG|REJECT", "material_type": "...", ...}
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_message = f"""종목: {stock_name}
기사 제목: {title}
기사 본문: {body if body.strip() else '(없음)'}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    # JSON 파싱 (```json ... ``` 마크다운 블록 자동 제거)
    import re as _re
    text = response.content[0].text.strip()
    # 마크다운 코드블록 제거
    match = _re.search(r'\{.*\}', text, _re.DOTALL)
    if match:
        text = match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {
            "verdict": "FLAG",
            "material_type": "파싱오류",
            "reason": f"Claude 응답 파싱 실패: {str(e)[:20]}",
            "one_shot_risk": None
        }


# ============================================================================
# 통합 실행
# ============================================================================

def run_step_a(stock_name: str, title: str, body: str = "") -> dict:
    """
    Step A 전체 실행 (1차 + 2차).

    Args:
        stock_name: 종목명
        title: 기사 제목
        body: 기사 본문 (선택)

    Returns:
        dict: 판정 결과
    """
    # 1차: 키워드 필터
    result = keyword_filter(title, body)
    if result:
        return result  # 즉시 REJECT

    # 2차: Claude API
    return claude_filter(stock_name, title, body)


# ============================================================================
# 테스트
# ============================================================================

if __name__ == "__main__":
    # 파일럿 케이스
    test_cases = [
        {
            "stock_name": "피플바이오",
            "title": "FDA 혁신 의료기기 지정 신청 추진",
            "body": "회사가 자사 치매 진단 기술에 대해 FDA 신청 추진 발표...",
            "expected": "REJECT"
        },
        {
            "stock_name": "엑셀세라퓨틱스",
            "title": "중국 상해세포치료그룹 배지 공급 계약",
            "body": "중국 기업과 CGT 배지 공급 계약 체결 발표",
            "expected": "FLAG"
        },
        {
            "stock_name": "가상사",
            "title": "방산부품 1,200억 수주 확정",
            "body": "국방부 발주 방산부품 대규모 수주 계약 체결",
            "expected": "PASS"
        },
        {
            "stock_name": "가상사2",
            "title": "2차전지 사업 진출 검토",
            "body": "이사회에서 2차전지 사업 진출 검토하기로 결의",
            "expected": "REJECT"
        },
    ]

    print("=" * 70)
    print("Step A 필터 테스트")
    print("=" * 70)

    for i, case in enumerate(test_cases, 1):
        result = run_step_a(
            stock_name=case["stock_name"],
            title=case["title"],
            body=case.get("body", "")
        )

        verdict = result.get("verdict")
        expected = case["expected"]
        status = "✅" if verdict == expected else "❌"

        print(f"\n[{i}] {case['stock_name']}")
        print(f"  기사: {case['title'][:40]}...")
        print(f"  결과: {verdict} {status} (예상: {expected})")
        print(f"  유형: {result.get('material_type')}")
        print(f"  이유: {result.get('reason')}")
        print(f"  단발성 위험: {result.get('one_shot_risk')}")
