import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 레이아웃 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# 2. 통합 디자인 CSS
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
    
    /* 기사 및 내용 박스 줄바꿈 처리 */
    .content-box {
        white-space: pre-wrap !important;
        word-break: break-all !important;
        line-height: 1.6 !important;
    }
</style>
""", unsafe_allow_html=True)

# 3. 유틸리티 함수
def get_sort_value(text, keyword):
    if pd.isna(text) or not keyword: return (0, 0)
    pattern = re.escape(keyword) + r'(\d+)-?(\d*)'
    match = re.search(pattern, str(text).replace(" ", ""))
    if match:
        main = int(match.group(1))
        sub = int(match.group(2)) if match.group(2) else 0
        return (main, sub)
    return (0, 0)

@st.cache_data
def load_data():
    if os.path.exists("data.xlsx"):
        return pd.read_excel("data.xlsx")
    return None

df = load_data()

if df is not None:
    # --- 세션 상태 관리 (초기화) ---
    if 'selected_stock' not in st.session_state:
        st.session_state.selected_stock = ""
    if 'search_keyword' not in st.session_state:
        st.session_state.search_keyword = ""
    if 'menu_index' not in st.session_state:
        st.session_state.menu_index = 0  # 0: 필터, 1: 상세분석

    # 사이드바 메뉴 (st.session_state.menu_index에 따라 연동)
    menu_options = ["🔎 전체 테마 필터", "📈 종목 상세 분석"]
    menu = st.sidebar.radio("기능 선택", menu_options, index=st.session_state.menu_index, key="main_menu")

    # 메뉴 전환 감지 (사용자가 수동으로 클릭했을 때 index 동기화)
    st.session_state.menu_index = menu_options.index(menu)

    # 1. [🔎 전체 테마 필터] 화면
    if menu == "🔎 전체 테마 필터":
        st.title("🔎 테마별 종목 정렬 필터")
        
        all_cols = df.columns.tolist()
        default_col = "코어테마" if "코어테마" in all_cols else all_cols[0]
        target_col = st.sidebar.selectbox("검색 기준 열", all_cols, index=all_cols.index(default_col))
        
        # 기존 검색어 유지
        keyword = st.text_input(f"[{target_col}] 검색어 입력", value=st.session_state.search_keyword)
        st.session_state.search_keyword = keyword # 검색어 저장

        if keyword:
            res = df[df[target_col].astype(str).str.contains(keyword, na=False)].copy()
            if not res.empty:
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, keyword))
                res = res.sort_values(by='sort_key', ascending=False)
                
                st.success(f"'{keyword}' 검색 결과: {len(res)}건")
                
                # [개선 1] 종목 선택 시 자동 페이지 전환
                selected = st.selectbox("상세 분석을 원하는 종목을 선택하세요", ["선택 안함"] + res['종목명'].tolist())
                if selected != "선택 안함":
                    st.session_state.selected_stock = selected
                    st.session_state.menu_index = 1 # 상세 분석 메뉴로 인덱스 변경
                    st.rerun() # 앱 재실행하여 즉시 이동

                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning("검색 결과가 없습니다.")

    # 2. [📈 종목 상세 분석] 화면
    elif menu == "📈 종목 상세 분석":
        st.title("📈 종목별 상세 분석")
        
        search_query = st.text_input("분석할 종목명을 입력하세요", value=st.session_state.selected_stock)

        if search_query:
            detail_res = df[df['종목명'].astype(str).str.contains(search_query, na=False, case=False)]
            if not detail_res.empty:
                row = detail_res.iloc[0]
                st.subheader(f"🔍 {row['종목명']} 데이터 요약")
                
                tabs = st.tabs(["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 상세내용", "📊 K스윙"])
                
                # [개선 3] 기사 탭 줄바꿈 반영 (content-box 클래스 적용 및 write 대신 markdown 사용)
                with tabs[0]: 
                    content = str(row.get("기사", "데이터 없음")).replace("_x000D_", "\n") # 엑셀 특수 줄바꿈 처리
                    st.markdown(f'<div class="content-box">{content}</div>', unsafe_allow_html=True)
                
                # 나머지 탭 유지
                with tabs[1]: st.markdown(f'<div class="content-box">{row.get("코어테마", "데이터 없음")}</div>', unsafe_allow_html=True)
                with tabs[2]: st.markdown(f'<div class="content-box">{row.get("대장이력", "데이터 없음")}</div>', unsafe_allow_html=True)
                with tabs[3]: st.success(row.get("키워드요약", "데이터 없음"))
                with tabs[4]: st.markdown(f'<div class="content-box">{row.get("전체테마", "데이터 없음")}</div>', unsafe_allow_html=True)
                with tabs[5]: st.markdown(f'<div class="content-box">{row.get("더 긴 설명", "데이터 없음")}</div>', unsafe_allow_html=True)
                with tabs[6]: st.markdown(f'<div class="content-box">{row.get("K스윙 정리", "데이터 없음")}</div>', unsafe_allow_html=True)
            else:
                st.warning("일치하는 종목이 없습니다.")
                
        # 다시 돌아가기 버튼 (옵션)
        if st.button("⬅ 필터 화면으로 돌아가기"):
            st.session_state.menu_index = 0
            st.rerun()
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
