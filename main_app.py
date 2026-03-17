import streamlit as st
import pandas as pd
import re
import os
from streamlit_searchbox import st_searchbox

# 1. 페이지 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide")

# --- 유틸리티 함수 (기존 로직 유지) ---
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
    match = re.search(pattern, str(text).replace(" ", ""))
    if match:
        main = int(match.group(1))
        sub = int(match.group(2)) if match.group(2) else 0
        return (main, sub)
    return (0, 0)

# --- 데이터 로드 (엑셀과 텍스트 리스트 모두 로드) ---
@st.cache_data
def load_all_data():
    df = None
    if os.path.exists("data.xlsx"):
        df = pd.read_excel("data.xlsx", engine='openpyxl')
    
    themes = []
    if os.path.exists("theme_list.txt"):
        with open("theme_list.txt", "r", encoding="utf-8") as f:
            themes = [line.strip() for line in f if line.strip()]
    return df, themes

df, unique_themes = load_all_data()

if df is not None:
    # 세션 상태 초기화 (메뉴 이동 시 데이터 유지용)
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""

    # --- [핵심] 테마 검색 엔진 (리스트 외 입력 허용) ---
    def search_theme(search_term):
        if not search_term:
            return []
        
        # 1. 초성 검색 여부 확인
        is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ " for char in search_term)
        
        # 2. 추천 리스트에서 매칭되는 단어 찾기
        if unique_themes:
            if is_chosung:
                matches = [t for t in unique_themes if search_term in get_chosung(t)]
            else:
                matches = [t for t in unique_themes if search_term.lower() in t.lower()]
        else:
            matches = []

        # 3. [중요] 사용자가 친 단어를 무조건 검색 후보 1번에 추가
        # 리스트에 없는 '태양열'을 쳐도 선택 가능해짐
        if search_term not in matches:
            matches.insert(0, search_term)
            
        return matches[:15]

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
    st.sidebar.title("💎 주식 통합 분석")
    menu = st.sidebar.radio("메뉴 선택", ["🔎 테마 필터", "📈 종목 상세 분석"])

    # 1. 테마 필터 화면
    if menu == "🔎 테마 필터":
        st.title("🔎 테마별 종목 정렬 필터")
        selected_theme = st_searchbox(
            search_theme, 
            key="theme_search", 
            placeholder="테마명 입력 (추천 리스트 외 직접 입력 가능)"
        )

        if selected_theme:
            # 엑셀의 '코어테마' 열에서 선택한 단어 포함 여부 검색
            res = df[df['코어테마'].astype(str).str.contains(selected_theme, na=False)].copy()
            if not res.empty:
                # 숫자 가중치 정렬 (태양광10 > 태양광2)
                res['sort_key'] = res['코어테마'].apply(lambda x: get_sort_value(x, selected_theme))
                res = res.sort_values(by='sort_key', ascending=False)
                
                st.success(f"'{selected_theme}' 검색 결과: {len(res)}건 (숫자 순 정렬 완료)")
                
                # 상세 이동용 보조 선택창
                move_target = st.selectbox("상세 정보를 보려면 종목을 선택하세요", ["선택 안함"] + res['종목명'].tolist())
                if move_target != "선택 안함":
                    st.session_state.selected_stock = move_target
                    st.info(f"'{move_target}'이(가) 선택되었습니다. 왼쪽 메뉴에서 '종목 상세 분석'을 클릭하세요.")
                
                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning(f"'{selected_theme}' 글자가 포함된 테마 데이터가 없습니다.")

    # 2. 종목 상세 분석 화면
    elif menu == "📈 종목 상세 분석":
        st.title("📈 종목 상세 분석")
        selected_stock = st_searchbox(
            search_stock, 
            key="stock_detail", 
            default=st.session_state.selected_stock,
            placeholder="종목명 또는 초성 입력"
        )

        if selected_stock:
            st.session_state.selected_stock = selected_stock
            row = df[df['종목명'] == selected_stock].iloc[0]
            st.subheader(f"🔍 {selected_stock} 분석 리포트")
            
            tabs = st.tabs(["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 기사본문", "📊 K스윙"])
            mapping = {0:"기사", 1:"코어테마", 2:"대장이력", 3:"키워드요약", 4:"전체테마", 5:"기사본문", 6:"K스윙 정리"}
            
            for i, col_name in mapping.items():
                with tabs[i]:
                    val = str(row.get(col_name, "정보 없음")).replace("_x000D_", "\n").strip()
                    st.markdown(f'<div style="white-space:pre-wrap; background:#f8f9fa; padding:20px; border-radius:10px; border:1px solid #e9ecef;">{val}</div>', unsafe_allow_html=True)
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다. 파일을 확인해 주세요.")
