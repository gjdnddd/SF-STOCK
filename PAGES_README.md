# GitHub Pages 배포 안내 (종목 히스토리)

Streamlit 앱(`main_app.py`)이 자꾸 잠들어서, 같은 기능을 **정적 웹페이지(GitHub Pages)** 로 다시 만든 것.
서버가 없어서 절대 잠들지 않는다. Streamlit 앱은 Pages 검증이 끝날 때까지 **그대로 유지**한다(`main_app.py`는 건드리지 않음).

- 사이트 주소: `https://gjdnddd.github.io/SF-STOCK/` (Pages 활성화 후)
- 소스: `pages/` (index.html, style.css, app.js) — 데이터 없는 순수 화면 코드
- 데이터 변환: `scripts/build_pages.py` — `종목_히스토리.xlsx` + `theme_list.txt` → JSON
- 배포: `.github/workflows/pages.yml` — GitHub Actions가 자동 실행

## 데이터 흐름 (엑셀 갱신 PC가 알아야 할 것 전부)

```
[엑셀 갱신 PC] xlsx 수정 → git commit → git push (main)
        │
        ├─▶ GitHub Actions: build_pages.py 로 JSON 생성 → Pages 자동 재배포   (신규)
        ├─▶ Streamlit Cloud: main 변경 감지 → 앱 재배포                      (기존, 당분간 유지)
        └─▶ 리눅스 서버: 매일 06:00 git pull → BigQuery 적재                 (기존, nextmove/run_db_sync.sh)
```

**엑셀 갱신 PC가 할 일은 기존과 같다: `종목_히스토리.xlsx` 를 push 하는 것뿐.**
JSON은 push 할 필요 없고, 하면 안 된다. JSON은 `_site/` 에만 생기고 `.gitignore` 로 제외되어 있으며 Actions가 배포 때마다 새로 만든다.

## 엑셀 갱신 PC 체크리스트 (중요)

1. **Pages 관련 파일이 main에 추가된 뒤 처음 한 번, 그 PC에서 `git pull` 을 먼저 할 것.**
   이 커밋이 main에 올라가면 그 PC의 로컬 main이 뒤처진다. 자동 push 스크립트가 `git pull` 없이 바로 `git push` 하면
   `rejected (non-fast-forward)` 로 거절될 수 있다.
2. 자동 push 스크립트는 push 직전에 pull 하도록 바꾸는 것을 권장:
   ```bash
   git pull --rebase --autostash origin main
   git add 종목_히스토리.xlsx
   git commit -m "종목_히스토리 업데이트 - $(date '+%Y-%m-%d %H:%M')"
   git push origin main
   ```
   커밋 메시지 형식(`종목_히스토리 업데이트 - YYYY-MM-DD HH:MM`)은 기존과 동일하게 유지한다.
3. `종목_히스토리.xlsx` 의 **컬럼 이름을 바꾸지 말 것.** 빌드 스크립트가 아래 컬럼을 이름으로 찾는다.
   `종목명, 코어테마, 전체테마, 대장이력, 기사, 키워드요약, 기사본문, K스윙 정리`
   (기존 Streamlit 앱도 같은 이름을 쓰므로 변경하면 둘 다 깨진다.) 컬럼이 없으면 Actions 빌드가 **실패하고 배포를 하지 않는다**(기존 사이트는 그대로 남음).
4. 테마 키워드 추가: 웹 화면에서는 추가할 수 없다(정적 페이지라 서버 저장 불가). `theme_list.txt` 에 한 줄 추가 후 push 하면 자동 반영된다.
   (Streamlit 사이드바의 "테마 리스트 추가"는 Streamlit 앱에서만 계속 동작.)
5. push 후 **1~2분 뒤** 사이트 하단 좌측 "데이터 갱신: 날짜" 가 바뀌었는지 보면 반영 여부를 알 수 있다.

## 최초 1회 설정 (사람이 GitHub 웹에서)

Pages를 켜는 것은 레포 설정이라 코드로 못 한다.
GitHub 레포 → **Settings → Pages → Build and deployment → Source: `GitHub Actions`** 선택.
그 뒤 **Actions 탭 → "Deploy GitHub Pages" → Run workflow** 로 첫 배포를 실행하면 된다.

## 로컬에서 확인 / 수정할 때

```bash
pip install pandas openpyxl
python scripts/build_pages.py          # _site/ 생성 (xlsx → JSON)
cd _site && python -m http.server 8765 # http://localhost:8765
```

- 화면/검색 로직 수정: `pages/app.js`, `pages/style.css`, `pages/index.html`
- 검색 규칙은 기존 `main_app.py` 와 동일하게 옮긴 것(초성 검색, 완전일치 시 숫자·기호 제거, 코어테마 숫자 내림차순 정렬).
  Streamlit과 다른 점: 빈 셀이 `nan` 으로 매칭되지 않고 "정보 없음"으로 표시됨, 검색어 입력 시 Enter 없이 바로 반영.

## 데이터 구조 (`_site/data/`)

| 파일 | 내용 | 로딩 시점 |
|---|---|---|
| `light.json` | 종목명, 코어테마, 전체테마, 대장이력 (약 0.4MB) | 페이지 열 때 |
| `article.json` `keyword.json` `body.json` `kswing.json` | 무거운 텍스트 컬럼 (body 9MB 등) | 해당 컬럼을 검색 범위에 넣거나 상세 탭을 열 때 |
| `themes.json` | `theme_list.txt` 목록 | 페이지 열 때 |

## 문제 해결

- **Actions 실패**: Actions 탭에서 로그 확인. 대부분 xlsx 컬럼명 변경 또는 파일 깨짐(행 100개 미만이면 일부러 실패시킴).
- **사이트가 안 바뀜**: xlsx 가 아니라 다른 파일만 push 했을 수 있다(트리거는 `종목_히스토리.xlsx`, `theme_list.txt`, `pages/**`, `scripts/build_pages.py`). Actions 탭에서 수동 실행 가능.
- **push 거절(non-fast-forward)**: 위 체크리스트 1~2번.
