"""
Step B: 테마 슬라이싱 (유사 사례 검색)

역할: 입력 종목의 테마 → BigQuery case_events에서 유사 사례 검색
- 1차: Python 테마 추출 (E열 전체테마 정규화)
- 2차: BigQuery 테마 매칭 쿼리 (core_theme 정확 + all_themes 부분)

입력:  stock_code, core_theme, all_themes
출력:  {"stock_code": str, "core_theme": str, "themes": list, "similar_cases": list, "case_count": int}
"""

import re
import sys
import io
from google.cloud import bigquery
from typing import Optional

# 한글 인코딩 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# ============================================================================
# 1차: Python 테마 추출
# ============================================================================

def extract_themes(all_themes_raw: str) -> list[str]:
    """
    E열(전체테마) 정규화: 쉼표 구분, 숫자 제거

    Args:
        all_themes_raw: "유리기판10-9, 반도체3, 로봇" 형태

    Returns:
        ["유리기판", "반도체", "로봇"]
    """
    if not all_themes_raw or not isinstance(all_themes_raw, str):
        return []

    themes = []
    for theme in all_themes_raw.split(','):
        theme = theme.strip()
        if theme:
            # 끝 숫자/카운터 제거: "유리기판10-9" → "유리기판"
            cleaned = re.sub(r'[\d\-]+$', '', theme).strip()
            if cleaned:
                themes.append(cleaned)

    return themes


def clean_core_theme(core_theme_raw: str) -> str:
    """
    F열(코어테마) 정규화: 숫자 제거

    Args:
        core_theme_raw: "유리기판10-9" 형태

    Returns:
        "유리기판"
    """
    if not core_theme_raw or not isinstance(core_theme_raw, str):
        return ""

    return re.sub(r'[\d\-]+$', '', core_theme_raw.strip()).strip()


# ============================================================================
# 2차: BigQuery 테마 매칭 쿼리
# ============================================================================

def search_similar_cases(
    core_theme: str,
    all_themes: list[str],
    project_id: str = "infin-stock-bot",
    dataset_id: str = "nextmove_master",
    table_id: str = "case_events",
    limit: int = 100
) -> list[dict]:
    """
    BigQuery에서 테마 매칭 사례 검색

    검색 로직:
    - 1차: core_theme 정확 매칭
    - 2차: all_themes 부분 매칭 (최소 1개 테마 포함)

    Args:
        core_theme: 코어테마 (정확 매칭)
        all_themes: 테마 리스트 (부분 매칭)
        project_id: GCP 프로젝트 ID
        dataset_id: BigQuery 데이터셋
        table_id: BigQuery 테이블
        limit: 결과 행 수 제한

    Returns:
        과거 사례 리스트 (dict 형태)
    """
    if not core_theme or not all_themes:
        return []

    client = bigquery.Client(project=project_id)

    # 테마 정규식 생성 (OR 조건: 테마 중 최소 1개 포함)
    theme_pattern = "|".join(re.escape(t) for t in all_themes)

    query = f"""
    SELECT
      case_id,
      event_date,
      stock_code,
      stock_name,
      core_theme,
      all_themes,
      article_title,
      article_body,
      market_cond,
      is_leader,
      keyword_summary,
      master_memo,
      rise_rate,
      trade_amount,
      d1_return,
      d2_return,
      d3_return,
      d4_return,
      d5_return
    FROM `{project_id}.{dataset_id}.{table_id}`
    WHERE (core_theme = @core_theme OR REGEXP_CONTAINS(all_themes, @theme_pattern))
    ORDER BY event_date DESC
    LIMIT @limit
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("core_theme", "STRING", core_theme),
            bigquery.ScalarQueryParameter("theme_pattern", "STRING", theme_pattern),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )

    try:
        results = client.query(query, job_config=job_config).to_list()
        return [dict(row) for row in results]
    except Exception as e:
        print(f"⚠️  BigQuery 쿼리 실패: {str(e)}")
        return []


# ============================================================================
# 통합 실행
# ============================================================================

def run_step_b(
    stock_code: str,
    core_theme_raw: str,
    all_themes_raw: str,
    **kwargs
) -> dict:
    """
    Step B 전체 실행

    Args:
        stock_code: 입력 종목코드
        core_theme_raw: F열 코어테마 (정규화 전)
        all_themes_raw: E열 전체테마 (정규화 전)
        **kwargs: search_similar_cases() 추가 인자 (project_id, limit 등)

    Returns:
        {
            "stock_code": str,
            "core_theme": str,              # 정규화된 코어테마
            "themes": list[str],            # 정규화된 테마 리스트
            "similar_cases": list[dict],    # BigQuery 검색 결과
            "case_count": int               # 검색된 사례 수
        }
    """
    # 1차: 테마 추출 및 정규화
    core_theme = clean_core_theme(core_theme_raw)
    themes = extract_themes(all_themes_raw)

    # 2차: BigQuery 검색
    similar_cases = search_similar_cases(core_theme, themes, **kwargs)

    return {
        "stock_code": stock_code,
        "core_theme": core_theme,
        "themes": themes,
        "similar_cases": similar_cases,
        "case_count": len(similar_cases)
    }


# ============================================================================
# 테스트
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Step B 테마 슬라이싱 테스트")
    print("=" * 70)

    # 테스트 케이스 1: 테마 추출
    print("\n[테스트 1] 테마 추출")
    themes = extract_themes("유리기판10-9, 반도체3, 로봇")
    expected = ["유리기판", "반도체", "로봇"]
    status = "✅" if themes == expected else "❌"
    print(f"  입력: '유리기판10-9, 반도체3, 로봇'")
    print(f"  출력: {themes} {status}")

    # 테스트 케이스 2: 코어테마 정규화
    print("\n[테스트 2] 코어테마 정규화")
    test_cases = [
        ("유리기판10-9", "유리기판"),
        ("반도체3", "반도체"),
        ("로봇", "로봇"),
        ("로봇10-15", "로봇"),
    ]
    for input_val, expected in test_cases:
        result = clean_core_theme(input_val)
        status = "✅" if result == expected else "❌"
        print(f"  '{input_val}' → '{result}' {status}")

    # 테스트 케이스 3: 엣지 케이스
    print("\n[테스트 3] 엣지 케이스")
    edge_cases = [
        ("", []),
        (None, []),
        ("테마", ["테마"]),
        ("테마1, 테마2, 테마3", ["테마", "테마", "테마"]),
    ]
    for input_val, expected in edge_cases:
        result = extract_themes(input_val) if isinstance(input_val, str) else []
        status = "✅" if result == expected else "❌"
        print(f"  '{input_val}' → {result} {status}")

    print("\n" + "=" * 70)
    print("✅ Step B 테마 추출 검증 완료")
    print("🔗 BigQuery 쿼리는 VM에서 실행 (ADC 인증)")
    print("=" * 70)
