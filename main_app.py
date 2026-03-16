import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 레이아웃 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide", initial_sidebar_state="expanded")

# 2. 통합 디자인 CSS
st.markdown("""
<style>
    /* 탭 가로 스크롤 및 디자인 */
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        display: flex !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        padding-bottom: 10px !important;
    }
    
    /* 표 레이아웃: 종목명 10%, 나머지 30% 균등 */
    .stTable { width: 100% !important; }
    th:nth-child(1), td:nth-child(1) { display: none !important; } 
    th:nth-child(2), td:nth-child(2) { width: 10% !important; text-align: center !important; font-weight: bold; }
    th:nth-child(3), td:nth-child(3),
    th:nth-child(4), td:nth-child(4),
    th:nth-child(5), td:nth-child(5) { width: 30% !important; }

    /* 내용 박스: 줄바꿈 정제 및 시인성 강화 */
    .content-box {
        white-space: pre-wrap !important;
        word-break: break-all !important;
        line-height: 1.6 !important;
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #e9ecef;
        color: #333;
        font-size: 15px;
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
        # 엑셀 파일 로드
        return pd.read_excel("data.xlsx")
    return None

df = load_data()

if df is not None:
    # 세션 상태 초기화
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'search_keyword' not in st.session_state: st.session_state.search_keyword = ""
    if 'page_view' not in st.session_state: st.session_state.page_view = "filter"

    # --- 사이드바 영역 ---
    with st.sidebar:
        st.title("💎 메뉴 설정")
        menu_choice = st.radio(
            "기능 선택", 
            ["🔎 전체 테마 필터", "📈 종목 상세 분석"], 
            index=0 if st.session_state.page_view == "filter" else 1
        )
        if menu_choice == "🔎 전체 테마 필터":
            st.session_state.page_view = "filter"
        else:
            st.session_state.page_view = "detail"
        
        st.divider()
        st.caption("사이드바를 접어 화면을 넓게 활용하세요.")

    # 1. [🔎 전체 테마 필터 화면]
    if st.session_state.page_view == "filter":
        st.title("🔎 테마별 종목 정렬 필터")
        
        all_cols = df.columns.tolist()
        target_col = st.selectbox("검색 기준 열 선택", all_cols, index=all_cols.index("코어테마") if "코어테마" in all_cols else 0)
        
        keyword = st.text_input(f"[{target_col}] 검색어 입력", value=st.session_state.search_keyword)
        st.session_state.search_keyword = keyword 

        if keyword:
            res = df[df[target_col].astype(str).str.contains(keyword, na=False)].copy()
            if not res.empty:
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, keyword))
                res = res.sort_values(by='sort_key', ascending=False)
                
                st.success(f"'{keyword}' 검색 결과: {len(res)}건")
                
                def move_to_detail():
                    if st.session_state.stock_selector != "선택 안함":
                        st.session_state.selected_stock = st.session_state.stock_selector
                        st.session_state.page_view = "detail"

                st.selectbox(
                    "상세 분석으로 이동할 종목 선택", 
                    ["선택 안함"] + res['종목명'].tolist(), 
                    key="stock_selector",
                    on_change=move_to_detail
                )

                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning("검색 결과가 없습니다.")

    # 2. [📈 종목 상세 분석 화면]
    elif st.session_state.page_view == "detail":
        header_col1, header_col2 = st.columns([8, 2])
        
        with header_col1:
            new_query = st.text_input("종목명 입력", value=st.session_state.selected_stock, label_visibility="collapsed", placeholder="분석할 종목명을 입력하세요")
            if new_query != st.session_state.selected_stock:
                st.session_state.selected_stock = new_query
                st.rerun()

        with header_col2:
            if st.button("⬅ 필터화면", use_container_width=True):
                st.session_state.page_view = "filter"
                st.rerun()

        st.divider()

        if st.session_state.selected_stock:
            detail_res = df[df['종목명'].astype(str).str.contains(st.session_state.selected_stock, na=False, case=False)]
            
            if not detail_res.empty:
                row = detail_res.iloc[0]
                st.subheader(f"🔍 {row['종목명']} 상세 분석")
                
                # 탭 구성: '상세내용'을 '기사본문'으로 변경
                tab_titles = ["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 기사본문", "📊 K스윙"]
                tabs = st.tabs(tab_titles)
                
                # 탭별 인덱스와 엑셀 컬럼명 매핑
                mapping = {
                    0: "기사",
                    1: "코어테마",
                    2: "대장이력",
                    3: "키워드요약",
                    4: "전체테마",
                    5: "기사본문", # 엑셀의 '기사본문' 컬럼 데이터 출력
                    6: "K스윙 정리"
                }

                for i, col_name in mapping.items():
                    with tabs[i]:
                        val = row.get(col_name, "정보 없음")
                        
                        # 데이터 정제 (엑셀 특수 줄바꿈 기호 처리)
                        content = str(val).replace("_x000D_", "\n").replace("\r", "")
                        content = re.sub(r'\n\s*\n', '\n', content).strip()
                        
                        if col_name == "키워드요약":
                            st.success(content)
                        else:
                            st.markdown(f'<div class="content-box">{content}</div>', unsafe_allow_html=True)
            else:
                st.warning("일치하는 종목이 없습니다.")

else:
    st.error("data.xlsx 파일을 찾을 수 없습니다. 파일명을 확인해 주세요.")
