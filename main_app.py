import streamlit as st
import pandas as pd
import re
import os

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
    # 세션 상태 강제 동기화
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'menu_option' not in st.session_state: st.session_state.menu_option = "🔎 테마 필터"

    # 사이드바
    st.sidebar.title("💎 주식 분석")
    st.session_state.menu_option = st.sidebar.radio("메뉴", ["🔎 테마 필터", "📈 종목 상세 분석"], index=0 if st.session_state.menu_option == "🔎 테마 필터" else 1)

    # 1. 테마 필터 화면
    if st.session_state.menu_option == "🔎 테마 필터":
        st.title("🔎 테마별 종목 정렬 필터")
        
        # [백스페이스 해결] selectbox + text_input 하이브리드 방식
        search_input = st.text_input("검색어 입력 (예: 태양광, ㅌㅇㄱ)", key="theme_input")
        
        if search_input:
            is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_input)
            # 추천 리스트 필터링
            filtered_themes = [t for t in unique_themes if (search_input in get_chosung(t) if is_chosung else search_input.lower() in t.lower())]
            # 입력한 단어를 무조건 0순위로
            if search_input not in filtered_themes:
                filtered_themes.insert(0, search_input)
            
            selected_theme = st.selectbox("추천 검색어 선택", filtered_themes, key="theme_select")
            
            if selected_theme:
                res = df[df['코어테마'].astype(str).str.contains(selected_theme, na=False, case=False)].copy()
                if not res.empty:
                    res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, selected_theme))
                    res = res.sort_values(by='sort_key', ascending=False)
                    
                    st.divider()
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        target = st.selectbox("상세 분석으로 연결할 종목을 선택하세요", ["선택 안함"] + res['종목명'].tolist())
                    with col2:
                        st.write(" ") # 레이아웃 정렬용
                        if st.button("📈 상세페이지 이동", use_container_width=True):
                            if target != "선택 안함":
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

        # [데이터 전달 해결] 세션에 저장된 종목명을 기본값으로 설정
        all_stocks = df['종목명'].astype(str).tolist()
        # 세션 값이 리스트에 있으면 해당 인덱스, 없으면 0번
        default_idx = all_stocks.index(st.session_state.selected_stock) if st.session_state.selected_stock in all_stocks else 0
        
        # 종목 검색창 (안정적인 selectbox 사용)
        selected_stock = st.selectbox("분석할 종목을 선택하세요", all_stocks, index=default_idx)

        if selected_stock:
            st.session_state.selected_stock = selected_stock
            row = df[df['종목명'].astype(str) == selected_stock].iloc[0]
            st.subheader(f"🔍 {selected_stock} 분석 리포트")
            
            tabs = st.tabs(["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 기사본문", "📊 K스윙"])
            mapping = {0:"기사", 1:"코어테마", 2:"대장이력", 3:"키워드요약", 4:"전체테마", 5:"기사본문", 6:"K스윙 정리"}
            
            for i, col_name in mapping.items():
                with tabs[i]:
                    content = str(row.get(col_name, "정보 없음")).replace("_x000D_", "\n").strip()
                    st.markdown(f'<div style="white-space:pre-wrap; background:#f8f9fa; padding:20px; border-radius:10px; border:1px solid #e9ecef; color:#333; font-size:16px;">{content}</div>', unsafe_allow_html=True)
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
