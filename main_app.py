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

# --- [수정됨] 데이터 로드 로직: 인코딩 문제 완벽 해결 ---
@st.cache_data
def load_all_data():
    df = None
    if os.path.exists("data.xlsx"):
        df = pd.read_excel("data.xlsx", engine='openpyxl')
    
    themes = []
    if os.path.exists("theme_list.txt"):
        # 여러 인코딩 방식을 시도하여 한글 깨짐 및 로드 실패 방지
        for encoding in ['utf-8', 'cp949', 'euc-kr']:
            try:
                with open("theme_list.txt", "r", encoding=encoding) as f:
                    themes = [line.strip() for line in f if line.strip()]
                if themes: break # 로드 성공 시 중단
            except:
                continue
    return df, themes

df, unique_themes = load_all_data()

if df is not None:
    # --- [수정됨] 테마 검색 엔진: 매칭 로직 강화 ---
    def search_theme(search_term):
        if not search_term:
            return []
        
        search_term_lower = search_term.lower()
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        
        matches = []
        if unique_themes:
            if is_chosung:
                # 초성 매칭
                matches = [t for t in unique_themes if search_term in get_chosung(t)]
            else:
                # 일반 단어 포함 매칭
                matches = [t for t in unique_themes if search_term_lower in t.lower()]
        
        # [중요] 사용자가 입력한 단어가 리스트에 없어도 첫 번째 후보로 표시
        if search_term not in matches:
            matches.insert(0, search_term)
            
        return matches[:20] # 최대 20개 노출

    # --- 종목 검색 엔진 ---
    def search_stock(search_term):
        if not search_term: return []
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        all_stocks = df['종목명'].astype(str).tolist()
        if is_chosung:
            starts = [s for s in all_stocks if get_chosung(s).startswith(search_term)]
            contains = [s for s in all_stocks if search_term in get_chosung(s) and not get_chosung(s).startswith(search_term)]
        else:
            starts = [s for s in all_stocks if s.lower().startswith(search_term.lower())]
            contains = [s for s in all_stocks if search_term.lower() in s.lower() and not s.lower().startswith(search_term.lower())]
        return (starts + contains)[:15]

    # --- 화면 구성 ---
    menu = st.sidebar.radio("메뉴", ["🔎 테마 필터", "📈 종목 상세"])

    if menu == "🔎 테마 필터":
        st.title("🔎 테마별 종목 정렬 필터")
        
        # 파일 로드 상태 확인용 (문제 해결 후 삭제 가능)
        if not unique_themes:
            st.warning("⚠️ theme_list.txt를 읽지 못했습니다. 파일 내용이나 위치를 확인하세요.")
        else:
            st.info(f"✅ {len(unique_themes)}개의 테마 리스트가 로드되었습니다.")

        selected_theme = st_searchbox(
            search_theme, 
            key="theme_search", 
            placeholder="테마명 또는 초성 입력"
        )

        if selected_theme:
            res = df[df['코어테마'].astype(str).str.contains(selected_theme, na=False, case=False)].copy()
            if not res.empty:
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, selected_theme))
                res = res.sort_values(by='sort_key', ascending=False)
                st.success(f"'{selected_theme}' 검색 결과: {len(res)}건")
                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.error("데이터가 없습니다.")

    elif menu == "📈 종목 상세":
        # ... (상세 로직 생략) ...
        pass
else:
    st.error("data.xlsx가 없습니다.")
