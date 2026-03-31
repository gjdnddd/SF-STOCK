import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 설정 및 스타일 주입
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"], .stMarkdown, p, span { font-size: 16px !important; }
    h1 { font-size: 20px !important; font-weight: bold !important; }
    h2, h3 { font-size: 18px !important; font-weight: bold !important; }
    .stTable td, .stTable th { font-size: 15px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 상태 관리 및 유틸리티 ---
def update_target_stock():
    if st.session_state.target_select != "선택 안함":
        st.session_state.selected_stock = st.session_state.target_select

def move_to_detail():
    if st.session_state.selected_stock:
        st.session_state.menu_option = "📈 종목 상세 분석"

@st.cache_data
def load_all_data():
    df = None
    if os.path.exists("종목_히스토리_NEW.xlsx"):
        df = pd.read_excel("종목_히스토리_NEW.xlsx", engine='openpyxl')
    themes = []
    if os.path.exists("theme_list.txt"):
        for encoding in ['utf-8', 'cp949', 'euc-kr']:
            try:
                with open("theme_list.txt", "r", encoding=encoding) as f:
                    themes = [line.strip() for line in f if line.strip()]
                if themes: break
            except: continue
    return df, themes

def add_new_theme(new_theme):
    if new_theme:
        with open("theme_list.txt", "a", encoding="utf-8") as f:
            f.write(f"\n{new_theme}")
        st.sidebar.success(f"'{new_theme}' 추가 완료!")
        st.cache_data.clear()
        st.rerun()

# --- 데이터 로드 ---
df, unique_themes = load_all_data()

if df is not None:
    if 'menu_option' not in st.session_state: st.session_state.menu_option = "🔎 테마 필터"
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'saved_search_input' not in st.session_state: st.session_state.saved_search_input = ""
    if 'saved_search_cols' not in st.session_state: st.session_state.saved_search_cols = ["코어테마"]
    if 'saved_selected_keyword' not in st.session_state: st.session_state.saved_selected_keyword = None

    # 사이드바
    st.sidebar.title("💎 주식 분석")
    choice = st.sidebar.radio("메뉴", ["🔎 테마 필터", "📈 종목 상세 분석"], 
                              index=0 if st.session_state.menu_option == "🔎 테마 필터" else 1)
    
    st.sidebar.divider()
    st.sidebar.subheader("➕ 테마 리스트 업데이트")
    new_theme_input = st.sidebar.text_input("새 키워드 입력", key="new_theme_input")
    if st.sidebar.button("리스트에 추가"):
        add_new_theme(new_theme_input)

    if choice != st.session_state.menu_option:
        st.session_state.menu_option = choice
        st.rerun()

    # 1. 테마 필터 화면
    if st.session_state.menu_option == "🔎 테마 필터":
        st.title("🔎 테마 상세 필터")
        
        col_opt1, col_opt2 = st.columns([2, 1])
        with col_opt1:
            search_columns = st.multiselect("검색 범위", 
                ["코어테마", "전체테마", "기사", "대장이력", "키워드요약", "기사본문", "K스윙 정리"],
                default=st.session_state.saved_search_cols)
            st.session_state.saved_search_cols = search_columns
        with col_opt2:
            search_mode = st.radio("검색 방식", ["포함", "완전 일치"], horizontal=True)
        
        search_input = st.text_input("검색어", value=st.session_state.saved_search_input, key="theme_input")
        st.session_state.saved_search_input = search_input
        
        if search_input and search_columns:
            def get_chosung(text):
                CHOSUNG_LIST = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
                res = ""
                for char in str(text):
                    if '가' <= char <= '힣': res += CHOSUNG_LIST[(ord(char) - ord('가')) // 588]
                    else: res += char.lower()
                return res

            is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_input)
            filtered_themes = [t for t in unique_themes if (search_input in get_chosung(t) if is_chosung else search_input.lower() in t.lower())]
            if search_input not in filtered_themes: filtered_themes.insert(0, search_input)
            
            try: def_idx = filtered_themes.index(st.session_state.saved_selected_keyword) if st.session_state.saved_selected_keyword in filtered_themes else 0
            except: def_idx = 0
            selected_keyword = st.selectbox("확정 검색어 선택", filtered_themes, index=def_idx, key="theme_select")
            st.session_state.saved_selected_keyword = selected_keyword
            
            if selected_keyword:
                if search_mode == "완전 일치":
                    def check_exact_match(cell_value, keyword):
                        items = re.split(r'[,.\s]+', str(cell_value))
                        for item in items:
                            pure_name = re.sub(r'[0-9\-_]', '', item).strip()
                            if pure_name.lower() == keyword.lower():
                                return True
                        return False

                    cond = [df[col].astype(str).apply(lambda x: check_exact_match(x, selected_keyword)) for col in search_columns]
                else:
                    cond = [df[col].astype(str).str.contains(re.escape(selected_keyword), na=False, case=False) for col in search_columns]
                
                res = df[pd.concat(cond, axis=1).any(axis=1)].copy()
                
                if not res.empty:
                    def sort_v(text, kw):
                        m = re.search(re.escape(kw) + r'(\d+)', str(text).replace(" ", ""))
                        return int(m.group(1)) if m else 0
                    res['sort_key'] = res['코어테마'].apply(lambda x: sort_v(x, selected_keyword))
                    res = res.sort_values(by='sort_key', ascending=False)
                    
                    st.divider()
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.selectbox("상세 정보를 볼 종목 선택", ["선택 안함"] + res['종목명'].tolist(), 
                                     key="target_select", on_change=update_target_stock)
                    with col2:
                        st.write(" ")
                        st.button("📈 상세페이지 이동", on_click=move_to_detail, use_container_width=True)

                    st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])

    # 2. 종목 상세 분석 화면
    elif st.session_state.menu_option == "📈 종목 상세 분석":
        st.title("📈 종목 상세 분석")
        if st.button("⬅️ 필터화면으로 돌아가기"):
            st.session_state.menu_option = "🔎 테마 필터"
            st.rerun()

        all_stocks = df['종목명'].astype(str).tolist()
        try: default_idx = all_stocks.index(st.session_state.selected_stock)
        except: default_idx = 0
            
        selected_stock = st.selectbox("종목 선택", all_stocks, index=default_idx, key="detail_stock_select")

        if selected_stock:
            st.session_state.selected_stock = selected_stock
            row = df[df['종목명'].astype(str) == selected_stock].iloc[0]
            st.subheader(f"🔍 {selected_stock} 분석 리포트")
            
            tabs = st.tabs(["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 기사본문", "📊 K스윙"])
            mapping = {0:"기사", 1:"코어테마", 2:"대장이력", 3:"키워드요약", 4:"전체테마", 5:"기사본문", 6:"K스윙 정리"}
            
            for i, col_name in mapping.items():
                with tabs[i]:
                    content = str(row.get(col_name, "정보 없음")).replace("_x000D_", "\n").strip()
                    st.markdown(f'<div style="white-space:pre-wrap; background:#f8f9fa; padding:15px; border-radius:10px; border:1px solid #e9ecef; color:#333; line-height:1.6;">{content}</div>', unsafe_allow_html=True)
else:
    st.error("종목_히스토리_NEW.xlsx 파일을 찾을 수 없습니다.")
