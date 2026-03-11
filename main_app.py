import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 레이아웃 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# 2. 통합 디자인 CSS (표 레이아웃 및 텍스트 박스)
st.markdown("""
<style>
    /* 탭 가로 스크롤 활성화 */
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        display: flex !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        padding-bottom: 10px !important;
    }
    
    /* [개선 3] 표 레이아웃: 종목명은 좁게, 나머지는 균등하게 */
    .stTable { width: 100% !important; }
    th:nth-child(1), td:nth-child(1) { display: none !important; } /* No열 숨김 */
    
    /* 종목명 (2열) */
    th:nth-child(2), td:nth-child(2) { width: 10% !important; text-align: center !important; font-weight: bold; }
    /* 코어/전체/이력 (3,4,5열) */
    th:nth-child(3), td:nth-child(3),
    th:nth-child(4), td:nth-child(4),
    th:nth-child(5), td:nth-child(5) { width: 30% !important; }

    div[data-testid="stTable"] td { 
        white-space: pre-wrap !important; 
        line-height: 1.5 !important;
        vertical-align: top !important;
    }

    /* [개선 1] 기사 내용 박스: 빈 줄 제거 및 촘촘한 줄바꿈 */
    .content-box {
        white-space: pre-wrap !important;
        word-break: break-all !important;
        line-height: 1.4 !important;
        background-color: #f9f9f9;
        padding: 10px;
        border-radius: 5px;
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

    # 사이드바 메뉴 (st.session_state.page_view와 직접 연동)
    st.sidebar.title("💎 주식 관리 도구")
    # 라디오 버튼의 선택값이 변경될 때 세션에 반영되도록 index 설정
    menu_map = {"filter": 0, "detail": 1}
    current_idx = menu_map.get(st.session_state.page_view, 0)
    
    menu = st.sidebar.radio(
        "기능 선택", 
        ["🔎 전체 테마 필터", "📈 종목 상세 분석"], 
        index=current_idx,
        key="nav_menu"
    )

    # 메뉴를 직접 클릭했을 때 세션 상태 업데이트
    if menu == "🔎 전체 테마 필터": st.session_state.page_view = "filter"
    else: st.session_state.page_view = "detail"

    # 1. [🔎 전체 테마 필터]
    if st.session_state.page_view == "filter":
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
                
                # [개선 2] 종목 선택 시 자동으로 상세페이지로 전환
                selected = st.selectbox("상세 분석을 원하는 종목을 선택하세요", ["선택 안함"] + res['종목명'].tolist(), key="stock_selector")
                if selected != "선택 안함":
                    st.session_state.selected_stock = selected
                    st.session_state.page_view = "detail" # 페이지 뷰 변경
                    st.rerun() # 즉시 재실행

                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning("검색 결과가 없습니다.")

    # 2. [📈 종목 상세 분석]
    elif st.session_state.page_view == "detail":
        st.title("📈 종목별 상세 분석")
        search_query = st.text_input("분석할 종목명을 입력하세요", value=st.session_state.selected_stock)

        if search_query:
            detail_res = df[df['종목명'].astype(str).str.contains(search_query, na=False, case=False)]
            if not detail_res.empty:
                row = detail_res.iloc[0]
                st.subheader(f"🔍 {row['종목명']} 데이터 요약")
                tabs = st.tabs(["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 상세내용", "📊 K스윙"])
                
                with tabs[0]: 
                    # [개선 1] 줄바꿈 정규화: 빈 칸(공백 라인) 제거 및 촘촘한 배치
                    raw_content = str(row.get("기사", "데이터 없음"))
                    # 엑셀 줄바꿈 및 불필요한 다중 줄바꿈을 단일 줄바꿈으로 치환
                    clean_content = raw_content.replace("_x000D_", "\n").replace("\r", "")
                    clean_content = re.sub(r'\n\s*\n', '\n', clean_content).strip() 
                    st.markdown(f'<div class="content-box">{clean_content}</div>', unsafe_allow_html=True)
                
                # 나머지 탭들도 일관성 있게 content-box 적용
                with tabs[1]: st.markdown(f'<div class="content-box">{row.get("코어테마", "")}</div>', unsafe_allow_html=True)
                with tabs[2]: st.markdown(f'<div class="content-box">{row.get("대장이력", "")}</div>', unsafe_allow_html=True)
                with tabs[3]: st.success(row.get("키워드요약", ""))
                with tabs[4]: st.markdown(f'<div class="content-box">{row.get("전체테마", "")}</div>', unsafe_allow_html=True)
                with tabs[5]: st.markdown(f'<div class="content-box">{row.get("더 긴 설명", "")}</div>', unsafe_allow_html=True)
                with tabs[6]: st.markdown(f'<div class="content-box">{row.get("K스윙 정리", "")}</div>', unsafe_allow_html=True)
            else:
                st.warning("일치하는 종목이 없습니다.")
        
        if st.button("⬅ 필터 화면으로 돌아가기"):
            st.session_state.page_view = "filter"
            st.rerun()
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
