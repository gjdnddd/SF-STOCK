import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 레이아웃 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# 2. 통합 디자인 CSS (상단 고정 바 및 표 레이아웃)
st.markdown("""
<style>
    /* 탭 가로 스크롤 활성화 */
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        display: flex !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        padding-bottom: 10px !important;
    }
    
    /* 상단 고정 영역 스타일 (Sticky Header) */
    .sticky-header {
        position: -webkit-sticky;
        position: sticky;
        top: 0;
        background-color: white;
        z-index: 1000;
        padding: 10px 0;
        border-bottom: 1px solid #ddd;
        margin-bottom: 20px;
    }

    /* 표 레이아웃 고정 */
    .stTable { width: 100% !important; }
    th:nth-child(1), td:nth-child(1) { display: none !important; } 
    th:nth-child(2), td:nth-child(2) { width: 10% !important; text-align: center !important; font-weight: bold; }
    th:nth-child(3), td:nth-child(3),
    th:nth-child(4), td:nth-child(4),
    th:nth-child(5), td:nth-child(5) { width: 30% !important; }

    /* 내용 박스 스타일 */
    .content-box {
        white-space: pre-wrap !important;
        word-break: break-all !important;
        line-height: 1.4 !important;
        background-color: #f9f9f9;
        padding: 15px;
        border-radius: 5px;
        border: 1px solid #eee;
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
    # 세션 상태 관리
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'search_keyword' not in st.session_state: st.session_state.search_keyword = ""
    if 'page_view' not in st.session_state: st.session_state.page_view = "filter"

    # 사이드바 메뉴 (내부 로직용으로만 사용하고 UI에서는 감출 수 있음)
    menu_options = ["🔎 전체 테마 필터", "📈 종목 상세 분석"]
    current_idx = 0 if st.session_state.page_view == "filter" else 1
    
    # 1. [🔎 전체 테마 필터 화면]
    if st.session_state.page_view == "filter":
        st.sidebar.title("💎 주식 관리 도구")
        st.sidebar.info("필터에서 종목 선택 시 자동 이동합니다.")
        
        st.title("🔎 테마별 종목 정렬 필터")
        all_cols = df.columns.tolist()
        target_col = st.sidebar.selectbox("검색 기준 열", all_cols, index=all_cols.index("코어테마") if "코어테마" in all_cols else 0)
        
        keyword = st.text_input(f"[{target_col}] 검색어 입력", value=st.session_state.search_keyword)
        st.session_state.search_keyword = keyword 

        if keyword:
            res = df[df[target_col].astype(str).str.contains(keyword, na=False)].copy()
            if not res.empty:
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, keyword))
                res = res.sort_values(by='sort_key', ascending=False)
                
                st.success(f"'{keyword}' 검색 결과: {len(res)}건")
                
                # 상세분석 종목 선택 (on_change를 사용해 확실한 자동 전환 구현)
                def on_stock_change():
                    if st.session_state.stock_selector != "선택 안함":
                        st.session_state.selected_stock = st.session_state.stock_selector
                        st.session_state.page_view = "detail"

                st.selectbox(
                    "상세 분석을 원하는 종목을 선택하세요", 
                    ["선택 안함"] + res['종목명'].tolist(), 
                    key="stock_selector",
                    on_change=on_stock_change
                )

                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning("검색 결과가 없습니다.")

    # 2. [📈 종목 상세 분석 화면]
    elif st.session_state.page_view == "detail":
        # --- 상단 고정 헤더 영역 ---
        header_col1, header_col2 = st.columns([8, 2])
        
        with header_col1:
            search_query = st.text_input("분석할 종목명을 입력하세요", value=st.session_state.selected_stock, label_visibility="collapsed")
            if search_query:
                st.session_state.selected_stock = search_query

        with header_col2:
            if st.button("⬅ 필터화면", use_container_width=True):
                st.session_state.page_view = "filter"
                st.rerun()

        st.divider() # 고정 느낌을 주기 위한 구분선

        # 상세 분석 데이터 출력
        if st.session_state.selected_stock:
            detail_res = df[df['종목명'].astype(str).str.contains(st.session_state.selected_stock, na=False, case=False)]
            if not detail_res.empty:
                row = detail_res.iloc[0]
                st.subheader(f"🔍 {row['종목명']} 분석 결과")
                
                tabs = st.tabs(["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 상세내용", "📊 K스윙"])
                
                with tabs[0]: 
                    raw_content = str(row.get("기사", "데이터 없음"))
                    clean_content = raw_content.replace("_x000D_", "\n").replace("\r", "")
                    clean_content = re.sub(r'\n\s*\n', '\n', clean_content).strip() 
                    st.markdown(f'<div class="content-box">{clean_content}</div>', unsafe_allow_html=True)
                
                with tabs[1]: st.markdown(f'<div class="content-box">{row.get("코어테마", "")}</div>', unsafe_allow_html=True)
                with tabs[2]: st.markdown(f'<div class="content-box">{row.get("대장이력", "")}</div>', unsafe_allow_html=True)
                with tabs[3]: st.success(row.get("키워드요약", ""))
                with tabs[4]: st.markdown(f'<div class="content-box">{row.get("전체테마", "")}</div>', unsafe_allow_html=True)
                with tabs[5]: st.markdown(f'<div class="content-box">{row.get("더 긴 설명", "")}</div>', unsafe_allow_html=True)
                with tabs[6]: st.markdown(f'<div class="content-box">{row.get("K스윙 정리", "")}</div>', unsafe_allow_html=True)
            else:
                st.warning("일치하는 종목이 없습니다.")

else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
