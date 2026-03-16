import streamlit as st
import pandas as pd
import re
import os
from streamlit_searchbox import st_searchbox

# 1. 페이지 레이아웃
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# 2. 초성 추출 함수
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

# 3. 데이터 로드 및 테마 단어 분리
@st.cache_data
def load_data():
    if not os.path.exists("data.xlsx"):
        return None
    df = pd.read_excel("data.xlsx")
    
    # [수정사항 2] 테마 단어 단위 분리 로직
    # 엑셀의 '코어테마' 컬럼에서 쉼표(,)나 공백 등으로 구분된 단어들을 모두 쪼개서 유니크한 리스트로 만듭니다.
    all_theme_series = df['코어테마'].dropna().astype(str)
    theme_words = set()
    for themes in all_theme_series:
        # 일반적인 구분자(쉼표, 슬래시, 세미콜론)로 쪼개기
        words = re.split(r'[,/;]|\s{2,}', themes) 
        for w in words:
            clean_w = w.strip()
            if clean_w: theme_words.add(clean_w)
    
    return df, sorted(list(theme_words))

df_data = load_data()

if df_data:
    df, unique_themes = df_data
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'page_view' not in st.session_state: st.session_state.page_view = "filter"

    # --- 공통 검색 엔진 (방법 B 스타일) ---
    def search_stock(search_term):
        if not search_term: return []
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        if is_chosung:
            return [s for s in df['종목명'].tolist() if search_term in get_chosung(s)]
        return [s for s in df['종목명'].tolist() if search_term.lower() in s.lower()]

    def search_theme(search_term):
        if not search_term: return []
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        if is_chosung:
            return [t for t in unique_themes if search_term in get_chosung(t)]
        return [t for t in unique_themes if search_term.lower() in t.lower()]

    # --- 사이드바 ---
    with st.sidebar:
        st.title("💎 메뉴 설정")
        menu = st.radio("기능 선택", ["🔎 전체 테마 필터", "📈 종목 상세 분석"], 
                        index=0 if st.session_state.page_view == "filter" else 1)
        st.session_state.page_view = "filter" if menu == "🔎 전체 테마 필터" else "detail"

    # --- 1. [🔎 전체 테마 필터] ---
    if st.session_state.page_view == "filter":
        st.title("🔎 테마별 종목 정렬 필터")
        
        # 실시간 테마 검색창
        selected_theme = st_searchbox(search_theme, key="theme_search", placeholder="테마명 또는 초성 입력 (예: ㄱㅌㅅ)")
        
        if selected_theme:
            res = df[df['코어테마'].astype(str).str.contains(selected_theme, na=False)].copy()
            st.success(f"'{selected_theme}' 관련 종목: {len(res)}건")
            
            # 여기서 선택하면 상세페이지로 이동
            move_stock = st.selectbox("상세 분석으로 이동", ["선택 안함"] + res['종목명'].tolist())
            if move_stock != "선택 안함":
                st.session_state.selected_stock = move_stock
                st.session_state.page_view = "detail"
                st.rerun()
            
            st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])

    # --- 2. [📈 종목 상세 분석] ---
    elif st.session_state.page_view == "detail":
        col1, col2 = st.columns([8, 2])
        with col2:
            if st.button("⬅ 필터화면", use_container_width=True):
                st.session_state.page_view = "filter"
                st.rerun()
        
        with col1:
            # 실시간 종목 검색창
            selected_stock = st_searchbox(search_stock, key="stock_search", 
                                          default=st.session_state.selected_stock,
                                          placeholder="종목명 또는 초성 입력 (예: ㅅㅅㅈㅈ)")
        
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
                    st.markdown(f'<div class="content-box" style="white-space: pre-wrap; background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; line-height: 1.6;">{content}</div>', unsafe_allow_html=True)
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
