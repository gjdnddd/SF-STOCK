import streamlit as st
import pandas as pd
import re
import os
from streamlit_searchbox import st_searchbox

# 1. 페이지 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# 2. 초성 추출 함수 (종목 상세 분석용)
def get_chosung(text):
    CHOSUNG_LIST = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
    result = ""
    for char in str(text):
        if '가' <= char <= '힣':
            char_code = ord(char) - ord('가')
            result += CHOSUNG_LIST[char_code // 588]
        else:
            result += char.lower()
    return result

# 정렬을 위한 숫자 추출 함수 (숫자 높은 순 정렬용)
def get_sort_value(text, keyword):
    if pd.isna(text) or not keyword: return (0, 0)
    # 키워드 뒤에 붙은 숫자를 찾음 (예: 태양광10 -> 10 추출)
    pattern = re.escape(keyword) + r'(\d+)-?(\d*)'
    match = re.search(pattern, str(text).replace(" ", ""))
    if match:
        main = int(match.group(1))
        sub = int(match.group(2)) if match.group(2) else 0
        return (main, sub)
    return (0, 0)

# 3. 데이터 로드
@st.cache_data
def load_data():
    if not os.path.exists("data.xlsx"):
        return None
    df = pd.read_excel("data.xlsx", engine='openpyxl')
    return df

df = load_data()

if df is not None:
    # 세션 상태 초기화
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'page_view' not in st.session_state: st.session_state.page_view = "filter"

    # --- 종목 검색용 엔진 (상세 분석 화면용) ---
    def search_stock(search_term):
        if not search_term: return []
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        all_stocks = df['종목명'].tolist()
        if is_chosung:
            starts = [s for s in all_stocks if get_chosung(s).startswith(search_term)]
            contains = [s for s in all_stocks if search_term in get_chosung(s) and not get_chosung(s).startswith(search_term)]
        else:
            starts = [s for s in all_stocks if s.lower().startswith(search_term.lower())]
            contains = [s for s in all_stocks if search_term.lower() in s.lower() and not s.lower().startswith(search_term.lower())]
        return (starts + contains)[:15]

    # --- 사이드바 ---
    with st.sidebar:
        st.title("💎 메뉴 설정")
        menu = st.radio("기능 선택", ["🔎 전체 테마 필터", "📈 종목 상세 분석"], 
                        index=0 if st.session_state.page_view == "filter" else 1)
        st.session_state.page_view = "filter" if menu == "🔎 전체 테마 필터" else "detail"

    # --- 1. [🔎 전체 테마 필터] (자유 입력 방식) ---
    if st.session_state.page_view == "filter":
        st.title("🔎 테마별 종목 정렬 필터")
        
        # [수정] 추천 리스트 없이 자유롭게 입력하는 방식
        keyword = st.text_input("검색할 테마명을 입력하세요", placeholder="예: 태양광, 원전, AI")
        
        if keyword:
            # 입력한 키워드가 포함된 모든 종목 검색
            res = df[df['코어테마'].astype(str).str.contains(keyword, na=False)].copy()
            
            if not res.empty:
                # 숫자 기준 정렬 (예: 태양광10이 상단으로)
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, keyword))
                res = res.sort_values(by='sort_key', ascending=False)
                
                st.success(f"'{keyword}' 검색 결과: {len(res)}건 (중요도 높은 순 정렬)")
                
                # 상세 분석 이동용 선택박스
                move_stock = st.selectbox("상세 분석으로 이동할 종목 선택", ["선택 안함"] + res['종목명'].tolist())
                if move_stock != "선택 안함":
                    st.session_state.selected_stock = move_stock
                    st.session_state.page_view = "detail"
                    st.rerun()
                
                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning(f"'{keyword}'를 포함하는 테마 데이터가 없습니다.")

    # --- 2. [📈 종목 상세 분석] (추천 리스트 방식 유지) ---
    elif st.session_state.page_view == "detail":
        col1, col2 = st.columns([8, 2])
        with col2:
            if st.button("⬅ 필터화면", use_container_width=True):
                st.session_state.page_view = "filter"
                st.rerun()
        
        with col1:
            # 종목은 추천 리스트가 나오는 것이 훨씬 편하므로 유지
            selected_stock = st_searchbox(search_stock, key="stock_search", 
                                          default=st.session_state.selected_stock,
                                          placeholder="종목명 입력 (ㅅㅅ -> 삼성전자 우선 추천)")
        
        if selected_stock:
            st.session_state.selected_stock = selected_stock
            row = df[df['종목명'] == selected_stock].iloc[0]
            st.subheader(f"🔍 {selected_stock} 상세 분석")
            
            tab_titles = ["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 기사본문", "📊 K스윙"]
            tabs = st.tabs(tab_titles)
            mapping = {0: "기사", 1: "코어테마", 2: "대장이력", 3: "키워드요약", 4: "전체테마", 5: "기사본문", 6: "K스윙 정리"}

            for i, col_name in mapping.items():
                with tabs[i]:
                    val = row.get(col_name, "정보 없음")
                    content = str(val).replace("_x000D_", "\n").replace("\r", "").strip()
                    st.markdown(f"""
                        <div style="white-space: pre-wrap; background-color: #f8f9fa; padding: 20px; 
                        border-radius: 10px; border: 1px solid #e9ecef; line-height: 1.6; color: #333;">
                            {content}
                        </div>
                    """, unsafe_allow_html=True)
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
