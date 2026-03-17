import streamlit as st
import pandas as pd
import re
import os
from streamlit_searchbox import st_searchbox

# 1. 페이지 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# --- 유틸리티 함수 ---
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

def get_sort_value(text, keyword):
    if pd.isna(text) or not keyword: return (0, 0)
    pattern = re.escape(keyword) + r'(\d+)-?(\d*)'
    match = re.search(pattern, str(text).replace(" ", ""), re.IGNORECASE)
    if match:
        main = int(match.group(1))
        sub = int(match.group(2)) if match.group(2) else 0
        return (main, sub)
    return (0, 0)

# --- 데이터 로드 ---
@st.cache_data
def load_all_data():
    df = None
    if os.path.exists("data.xlsx"):
        df = pd.read_excel("data.xlsx", engine='openpyxl')
    
    themes = []
    if os.path.exists("theme_list.txt"):
        for encoding in ['utf-8', 'cp949', 'euc-kr']:
            try:
                with open("theme_list.txt", "r", encoding=encoding) as f:
                    themes = [line.strip() for line in f if line.strip()]
                if themes: break
            except: continue
    return df, themes

df, unique_themes = load_all_data()

if df is not None:
    # 세션 상태 초기화
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'menu_option' not in st.session_state: st.session_state.menu_option = "🔎 테마 필터"

    # --- [수정] 테마 검색 엔진: 입력어 0순위 고정 ---
    def search_theme(search_term):
        if not search_term: return []
        search_term_lower = search_term.lower()
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        
        # 리스트 필터링
        matches = [t for t in unique_themes if (search_term in get_chosung(t) if is_chosung else search_term_lower in t.lower())]
        
        # 사용자가 입력한 단어가 리스트에 있든 없든 0순위로 강제 삽입 (엔터 시 우선 선택)
        if search_term in matches:
            matches.remove(search_term)
        matches.insert(0, search_term)
        
        return matches[:20]

    def search_stock(search_term):
        if not search_term: return []
        all_stocks = df['종목명'].astype(str).tolist()
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        if is_chosung:
            starts = [s for s in all_stocks if get_chosung(s).startswith(search_term)]
            contains = [s for s in all_stocks if search_term in get_chosung(s) and not get_chosung(s).startswith(search_term)]
        else:
            starts = [s for s in all_stocks if s.lower().startswith(search_term.lower())]
            contains = [s for s in all_stocks if search_term.lower() in s.lower() and not s.lower().startswith(search_term.lower())]
        return (starts + contains)[:15]

    # --- 사이드바 메뉴 ---
    st.session_state.menu_option = st.sidebar.radio("메뉴 선택", ["🔎 테마 필터", "📈 종목 상세 분석"], index=0 if st.session_state.menu_option == "🔎 테마 필터" else 1)

    # 1. 테마 필터 화면
    if st.session_state.menu_option == "🔎 테마 필터":
        st.title("🔎 테마별 종목 정렬 필터")
        
        # [수정] 포커스 유지를 위해 container 사용 및 전역 키 할당
        theme_container = st.container()
        with theme_container:
            selected_theme = st_searchbox(
                search_theme, 
                key="theme_search_box_unique", 
                placeholder="테마명 입력 후 엔터",
                edit_after_submit=True
            )

        if selected_theme:
            res = df[df['코어테마'].astype(str).str.contains(selected_theme, na=False, case=False)].copy()
            if not res.empty:
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, selected_theme))
                res = res.sort_values(by='sort_key', ascending=False)
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    target = st.selectbox("상세 정보를 볼 종목 선택", ["선택 안함"] + res['종목명'].tolist(), label_visibility="collapsed")
                with col2:
                    if st.button("📈 상세페이지로 이동") and target != "선택 안함":
                        st.session_state.selected_stock = target
                        st.session_state.menu_option = "📈 종목 상세 분석"
                        st.rerun()
                
                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])

    # 2. 종목 상세 분석 화면
    elif st.session_state.menu_option == "📈 종목 상세 분석":
        st.title("📈 종목 상세 분석")
        if st.button("⬅️ 필터화면으로 돌아가기"):
            st.session_state.menu_option = "🔎 테마 필터"
            st.rerun()

        selected_stock = st_searchbox(
            search_stock, 
            key="stock_search_box_unique", 
            default=st.session_state.selected_stock,
            edit_after_submit=True
        )

        if selected_stock:
            st.session_state.selected_stock = selected_stock
            row = df[df['종목명'].astype(str) == selected_stock].iloc[0]
            st.subheader(f"🔍 {selected_stock} 분석 리포트")
            
            tabs = st.tabs(["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 기사본문", "📊 K스윙"])
            mapping = {0:"기사", 1:"코어테마", 2:"대장이력", 3:"키워드요약", 4:"전체테마", 5:"기사본문", 6:"K스윙 정리"}
            
            for i, col_name in mapping.items():
                with tabs[i]:
                    content = str(row.get(col_name, "정보 없음")).replace("_x000D_", "\n").strip()
                    st.markdown(f'<div style="white-space:pre-wrap; background:#f8f9fa; padding:20px; border-radius:10px; border:1px solid #e9ecef; color:#333;">{content}</div>', unsafe_allow_html=True)
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
