import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 레이아웃 및 설정
st.set_page_config(page_title="주식 통합 분석 시스템", layout="wide", initial_sidebar_state="expanded")

# 2. 초성 추출 함수 (라이브러리 없이 구현)
def get_chosung(text):
    CHOSUNG_LIST = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
    result = ""
    for char in text:
        if '가' <= char <= '힣':
            char_code = ord(char) - ord('가')
            chosung_index = char_code // 588
            result += CHOSUNG_LIST[chosung_index]
        else:
            result += char
    return result

# 3. 통합 디자인 CSS
st.markdown("""
<style>
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        display: flex !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        padding-bottom: 10px !important;
    }
    .content-box {
        white-space: pre-wrap !important;
        word-break: break-all !important;
        line-height: 1.6 !important;
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #e9ecef;
        color: #333;
        font-size: 15px;
    }
</style>
""", unsafe_allow_html=True)

# 4. 데이터 로드 및 초기화
@st.cache_data
def load_data():
    if os.path.exists("data.xlsx"):
        df = pd.read_excel("data.xlsx")
        # 검색 효율을 위해 미리 초성 컬럼 생성
        df['종목명_초성'] = df['종목명'].apply(lambda x: get_chosung(str(x)))
        return df
    return None

df = load_data()

if df is not None:
    # 세션 상태 초기화
    if 'selected_stock' not in st.session_state: st.session_state.selected_stock = ""
    if 'page_view' not in st.session_state: st.session_state.page_view = "filter"

    # 사이드바 메뉴
    with st.sidebar:
        st.title("💎 메뉴 설정")
        menu_choice = st.radio("기능 선택", ["🔎 전체 테마 필터", "📈 종목 상세 분석"], 
                               index=0 if st.session_state.page_view == "filter" else 1)
        st.session_state.page_view = "filter" if menu_choice == "🔎 전체 테마 필터" else "detail"

    # --- 1. [🔎 전체 테마 필터] ---
    if st.session_state.page_view == "filter":
        st.title("🔎 테마별 종목 정렬 필터")
        
        # 테마 리스트 추출 (자동 리스트업)
        all_themes = sorted(list(set(df['코어테마'].dropna().astype(str))))
        
        search_input = st.text_input("테마 검색 (초성 검색 지원)", placeholder="예: ㄱㅌㅅ 또는 광통신")
        
        if search_input:
            # 초성인지 일반 텍스트인지 판별하여 필터링
            is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ" for char in search_input)
            if is_chosung:
                filtered_themes = [t for t in all_themes if search_input in get_chosung(t)]
            else:
                filtered_themes = [t for t in all_themes if search_input in t]
            
            if filtered_themes:
                selected_theme = st.selectbox(f"'{search_input}' 관련 테마 목록", filtered_themes)
                
                # 결과 출력
                res = df[df['코어테마'].astype(str).str.contains(selected_theme, na=False)].copy()
                st.success(f"'{selected_theme}' 검색 결과: {len(res)}건")
                
                # 종목 선택 시 바로 상세페이지 이동을 위한 기능
                target_stock = st.selectbox("상세 분석으로 이동할 종목 선택", ["선택 안함"] + res['종목명'].tolist())
                if target_stock != "선택 안함":
                    st.session_state.selected_stock = target_stock
                    st.session_state.page_view = "detail"
                    st.rerun()
                
                st.table(res[["종목명", "코어테마", "전체테마", "대장이력"]])
            else:
                st.warning("일치하는 테마 후보가 없습니다.")

    # --- 2. [📈 종목 상세 분석] ---
    elif st.session_state.page_view == "detail":
        col1, col2 = st.columns([8, 2])
        with col2:
            if st.button("⬅ 필터화면", use_container_width=True):
                st.session_state.page_view = "filter"
                st.rerun()
        
        with col1:
            # 종목명 검색 입력창 (초성 지원)
            stock_input = st.text_input("종목명 검색 (초성 가능)", value=st.session_state.selected_stock, placeholder="ㅅㅅㅈㅈ 또는 삼성전자")
        
        if stock_input:
            # 초성 검사 및 필터링
            is_chosung = all(char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ" for char in stock_input)
            if is_chosung:
                matches = df[df['종목명_초성'].str.contains(stock_input, na=False)]
            else:
                matches = df[df['종목명'].str.contains(stock_input, na=False, case=False)]
            
            if not matches.empty:
                stock_list = matches['종목명'].tolist()
                # 검색 결과가 여러개일 경우 선택박스 표시
                selected_stock = st.selectbox("검색된 종목 선택", stock_list, 
                                              index=stock_list.index(st.session_state.selected_stock) if st.session_state.selected_stock in stock_list else 0)
                
                if selected_stock:
                    row = df[df['종목명'] == selected_stock].iloc[0]
                    st.divider()
                    st.subheader(f"🔍 {selected_stock} 상세 분석")
                    
                    tab_titles = ["📰 기사", "🎯 코어테마", "🥇 대장이력", "💡 키워드요약", "🌐 전체테마", "📝 기사본문", "📊 K스윙"]
                    tabs = st.tabs(tab_titles)
                    
                    mapping = {0: "기사", 1: "코어테마", 2: "대장이력", 3: "키워드요약", 4: "전체테마", 5: "기사본문", 6: "K스윙 정리"}

                    for i, col_name in mapping.items():
                        with tabs[i]:
                            val = row.get(col_name, "정보 없음")
                            content = str(val).replace("_x000D_", "\n").replace("\r", "")
                            content = re.sub(r'\n\s*\n', '\n', content).strip()
                            
                            if col_name == "키워드요약":
                                st.success(content)
                            else:
                                st.markdown(f'<div class="content-box">{content}</div>', unsafe_allow_html=True)
            else:
                st.warning("검색 결과가 없습니다.")
else:
    st.error("data.xlsx 파일을 찾을 수 없습니다.")
