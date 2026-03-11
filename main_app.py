import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 레이아웃 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# 2. 통합 디자인 CSS (필터 표 + 상세조회 탭 스크롤)
st.markdown("""
<style>
    /* 탭 가로 스크롤 활성화 */
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        display: flex !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        padding-bottom: 10px !important;
    }
    /* 표 줄바꿈 및 상단 정렬 */
    div[data-testid="stTable"] td { 
        white-space: pre-wrap !important; 
        line-height: 1.5 !important;
        vertical-align: top !important;
    }
    /* 표의 첫 번째 인덱스 열 숨기기 */
    th:nth-child(1), td:nth-child(1) { display: none !important; }
    
    /* 필터 표 열 너비 고정 */
    th:nth-child(2), td:nth-child(2) { width: 10% !important; text-align: center !important; }
    th:nth-child(3), td:nth-child(3),
    th:nth-child(4), td:nth-child(4),
    th:nth-child(5), td:nth-child(5) { width: 30% !important; }
</style>
""", unsafe_allow_html=True)

# 3. 유틸리티 함수: 검색어 뒤의 숫자 추출 정렬용
def get_sort_value(text, keyword):
    if pd.isna(text) or not keyword: return (0, 0)
    # 검색어 뒤에 붙은 숫자를 찾음 (예: 반도체30-9)
    pattern = re.escape(keyword) + r'(\d+)-?(\d*)'
    match = re.search(pattern, str(text).replace(" ", ""))
    if match:
        main = int(match.group(1))
        sub = int(match.group(2)) if match.group(2) else 0
        return (main, sub)
    return (0, 0)

# 4. 데이터 로드
@st.cache_data
def load_data():
    if os.path.exists("data.xlsx"):
        return pd.read_excel("data.xlsx")
    return None

df = load_data()

if df is not None:
    # 세션 상태: 메뉴 간 종목 데이터 전달용
    if 'selected_stock' not in st.session_state:
        st.session_state.selected_stock = ""

    # 사이드바 메뉴 구성
    st.sidebar.title("💎 주식 관리 도구")
    menu = st.sidebar.radio("기능 선택", ["🔎 전체 테마 필터", "📈 종목 상세 분석"])

    if menu == "🔎 전체 테마 필터":
        st.title("🔎 테마별 종목 정렬 필터")
        
        # 검색 설정
        all_cols = df.columns.tolist()
        default_col = "코어테마" if "코어테마" in all_cols else all_cols[0]
        target_col = st.sidebar.selectbox("검색 기준 열", all_cols, index=all_cols.index(default_col))
        
        keyword = st.text_input(f"[{target_col}] 검색어 입력 (예: 반도체, 전력수요)")

        if keyword:
            # 필터링 및 숫자 기반 정렬
            res = df[df[target_col].astype(str).str.contains(keyword, na=False)].copy()
            if not res.empty:
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, keyword))
                res = res.sort_values(by='sort_key', ascending=False)
                
                st.success(f"'{keyword}' 검색 결과: {len(res)}건 (숫자 높은 순 정렬)")
                
                # 상세조회로 넘길 종목 선택 (필터링된 결과 중에서만 선택)
                selected = st.selectbox("상세 분석을 원하는 종목을 선택하세요", ["선택 안함"] + res['종목명'].tolist())
                if selected != "선택 안함":
                    st.session_state.selected_stock = selected
                    st.info(f"💡 사이드바 메뉴를 '📈 종목 상세 분석'으로 변경하면 {selected}의 상세 내용을 확인합니다.")

                # 결과 표 출력
                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning("검색 결과가 없습니다.")

    elif menu == "📈 종목 상세 분석":
        st.title("📈 종목별 상세 분석")
        
        # 필터에서 선택된 종목이 있으면 자동으로 입력됨
        search_query = st.text_input("분석할 종목명을 입력하세요", value=st.session_state.selected_stock)

        if search_query:
            # 종목명 열에서 검색
            detail_res = df[df['종목명'].astype(str).str.contains(search_query, na=False, case=False)]
            if not detail_res.empty:
                row = detail_res.iloc[0]
                st.subheader(f"🔍 {row['종목명']} 데이터 요약")
                
                # 탭 구성 (사용자 커스텀 탭)
                tabs = st.tabs(["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 상세내용", "📊 K스윙"])
                
                with tabs[0]: st.write(row.get("기사", "데이터 없음"))
                with tabs[1]: st.write(row.get("코어테마", "데이터 없음"))
                with tabs[2]: st.write(row.get("대장이력", "데이터 없음"))
                with tabs[3]: st.success(row.get("키워드요약", "데이터 없음"))
                with tabs[4]: st.write(row.get("전체테마", "데이터 없음"))
                with tabs[5]: st.write(row.get("더 긴 설명", "데이터 없음"))
                with tabs[6]: st.write(row.get("K스윙 정리", "데이터 없음"))
            else:
                st.warning("일치하는 종목이 없습니다.")
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다. 같은 폴더에 엑셀 파일을 업로드해 주세요.")