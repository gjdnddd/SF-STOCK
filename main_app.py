import streamlit as st
import pandas as pd
import re
import os
from streamlit_searchbox import st_searchbox

# 1. 페이지 설정
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

# 정렬을 위한 숫자 추출 함수 (기존 로직 유지)
def get_sort_value(text, keyword):
    if pd.isna(text) or not keyword: return (0, 0)
    pattern = re.escape(keyword) + r'(\d+)-?(\d*)'
    match = re.search(pattern, str(text).replace(" ", ""))
    if match:
        main = int(match.group(1))
        sub = int(match.group(2)) if match.group(2) else 0
        return (main, sub)
    return (0, 0)

# 3. 데이터 로드 및 테마 단어 정제
@st.cache_data
def load_data():
    if not os.path.exists("data.xlsx"):
        return None
    df = pd.read_excel("data.xlsx", engine='openpyxl')
    
    # 테마 단어 단위 분리 로직 강화 (숫자 제거 후 순수 단어만 추출)
    all_theme_series = df['코어테마'].dropna().astype(str)
    theme_words = set()
    for themes in all_theme_series:
        # 숫자와 기호 제거하고 단어만 분리
        words = re.split(r'[,/;]|\s{2,}', themes)
        for w in words:
            # "태양광5" -> "태양광"으로 변환
            clean_w = re.sub(r'\d+', '', w).strip()
            if clean_w: theme_words.add(clean_w)
    
    return df, sorted(list(theme_words))

load_res = load_data()

if load_res:
    df, unique_themes = load_res
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'page_view' not in st.session_state: st.session_state.page_view = "filter"

    # --- 🔎 검색 엔진 로직 수정 ---

    # [수정 1] 종목 검색: 시작하는 단어 우선 추천
    def search_stock(search_term):
        if not search_term: return []
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        
        all_stocks = df['종목명'].tolist()
        if is_chosung:
            # 초성으로 시작하는 것들
            starts = [s for s in all_stocks if get_chosung(s).startswith(search_term)]
            contains = [s for s in all_stocks if search_term in get_chosung(s) and not get_chosung(s).startswith(search_term)]
        else:
            # 글자로 시작하는 것들
            starts = [s for s in all_stocks if s.lower().startswith(search_term.lower())]
            contains = [s for s in all_stocks if search_term.lower() in s.lower() and not s.lower().startswith(search_term.lower())]
        
        return (starts + contains)[:15]

    # [수정 2] 테마 검색: 순수 단어만 추천
    def search_theme(search_term):
        if not search_term: return []
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        
        if is_chosung:
            matches = [t for t in unique_themes if search_term in get_chosung(t)]
        else:
            matches = [t for t in unique_themes if search_term.lower() in t.lower()]
        return matches[:15]

    # --- 사이드바 ---
    with st.sidebar:
        st.title("💎 메뉴 설정")
        menu = st.radio("기능 선택", ["🔎 전체 테마 필터", "📈 종목 상세 분석"], 
                        index=0 if st.session_state.page_view == "filter" else 1)
        st.session_state.page_view = "filter" if menu == "🔎 전체 테마 필터" else "detail"

    # --- 1. [🔎 전체 테마 필터] ---
    if st.session_state.page_view == "filter":
        st.title("🔎 테마별 종목 정렬 필터")
        
        # 이제 추천 결과는 '태양광', '원전' 등 깔끔한 단어로 나옴
        selected_theme = st_searchbox(search_theme, key="theme_search", placeholder="테마명 입력 (예: 태양광, 원전)")
        
        if selected_theme:
            # [수정 3] 선택한 테마가 포함된 모든 종목 검색 + 숫자 기준 정렬
            res = df[df['코어테마'].astype(str).str.contains(selected_theme, na=False)].copy()
            
            if not res.empty:
                # 가중치 정렬 (기존 get_sort_value 로직 적용)
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, selected_theme))
                res = res.sort_values(by='sort_key', ascending=False)
                
                st.success(f"'{selected_theme}' 관련 종목: {len(res)}건 (숫자 높은 순 정렬)")
                
                move_stock = st.selectbox("상세 분석으로 이동", ["선택 안함"] + res['종목명'].tolist())
                if move_stock != "선택 안함":
                    st.session_state.selected_stock = move_stock
                    st.session_state.page_view = "detail"
                    st.rerun()
                
                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning("일치하는 데이터가 없습니다.")

    # --- 2. [📈 종목 상세 분석] ---
    elif st.session_state.page_view == "detail":
        col1, col2 = st.columns([8, 2])
        with col2:
            if st.button("⬅ 필터화면", use_container_width=True):
                st.session_state.page_view = "filter"
                st.rerun()
        
        with col1:
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
                    st.markdown(f'<div class="content-box" style="white-space: pre-wrap; background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; line-height: 1.6;">{content}</div>', unsafe_allow_html=True)
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
