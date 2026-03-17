import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 설정 및 전체 글자 크기 CSS 주입
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# 모든 글자 크기를 검색창(약 16px) 수준으로 통일하는 CSS
st.markdown("""
    <style>
    /* 전체 텍스트 및 입력창 글자 크기 */
    html, body, [class*="css"], .stMarkdown, p, span {
        font-size: 16px !important;
    }
    /* 제목 및 헤더 크기 축소 */
    h1 { font-size: 20px !important; font-weight: bold !important; }
    h2, h3 { font-size: 18px !important; font-weight: bold !important; }
    /* 테이블 내부 글자 크기 */
    .stTable td, .stTable th {
        font-size: 15px !important;
    }
    /* 탭 메뉴 글자 크기 */
    button[data-baseweb="tab"] div {
        font-size: 16px !important;
    }
    /* 사이드바 메뉴 크기 */
    section[data-testid="stSidebar"] .stRadio div {
        font-size: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)

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
    if 'menu_option' not in st.session_state: st.session_state.menu_option = "🔎 테마 필터"
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'saved_search_input' not in st.session_state: st.session_state.saved_search_input = ""
    if 'saved_search_cols' not in st.session_state: st.session_state.saved_search_cols = ["코어테마"]
    if 'saved_selected_keyword' not in st.session_state: st.session_state.saved_selected_keyword = None

    # --- 사이드바 메뉴 (클릭 즉시 반응하도록 최적화) ---
    st.sidebar.title("💎 주식 분석")
    # radio의 값을 session_state에 직접 연결하여 버벅임 제거
    choice = st.sidebar.radio("메뉴", ["🔎 테마 필터", "📈 종목 상세 분석"], 
                              key="menu_radio_sync",
                              index=0 if st.session_state.menu_option == "🔎 테마 필터" else 1)
    
    # 메뉴 변경 시 상태 업데이트 및 리런
    if choice != st.session_state.menu_option:
        st.session_state.menu_option = choice
        st.rerun()

    # 1. 테마 필터 화면
    if st.session_state.menu_option == "🔎 테마 필터":
        st.title("🔎 테마 상세 필터")
        
        search_columns = st.multiselect(
            "검색 범위를 선택하세요",
            ["코어테마", "전체테마", "기사", "대장이력", "키워드요약", "기사본문", "K스윙 정리"],
            default=st.session_state.saved_search_cols
        )
        st.session_state.saved_search_cols = search_columns
        
        search_input = st.text_input("검색어 입력", value=st.session_state.saved_search_input, key="theme_input")
        st.session_state.saved_search_input = search_input
        
        if search_input and search_columns:
            is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_input)
            filtered_themes = [t for t in unique_themes if (search_input in get_chosung(t) if is_chosung else search_input.lower() in t.lower())]
            if search_input not in filtered_themes:
                filtered_themes.insert(0, search_input)
            
            try:
                def_idx = filtered_themes.index(st.session_state.saved_selected_keyword) if st.session_state.saved_selected_keyword in filtered_themes else 0
            except:
                def_idx = 0
                
            selected_keyword = st.selectbox("확정 검색어 선택", filtered_themes, index=def_idx, key="theme_select")
            st.session_state.saved_selected_keyword = selected_keyword
            
            if selected_keyword:
                conditions = [df[col].astype(str).str.contains(selected_keyword, na=False, case=False) for col in search_columns]
                res = df[pd.concat(conditions, axis=1).any(axis=1)].copy()
                
                if not res.empty:
                    res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, selected_keyword))
                    res = res.sort_values(by='sort_key', ascending=False)
                    
                    st.divider()
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        target = st.selectbox("상세 정보를 볼 종목 선택", ["선택 안함"] + res['종목명'].tolist(), key="target_select")
                    with col2:
                        st.write(" ")
                        if st.button("📈 상세페이지 이동", use_container_width=True) and target != "선택 안함":
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

        all_stocks = df['종목명'].astype(str).tolist()
        default_idx = all_stocks.index(st.session_state.selected_stock) if st.session_state.selected_stock in all_stocks else 0
        selected_stock = st.selectbox("종목 선택", all_stocks, index=default_idx)

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
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
