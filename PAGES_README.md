# GitHub Pages 배포 안내 (종목 히스토리)

Streamlit 앱(`main_app.py`)이 자꾸 잠들어서, 같은 기능을 **정적 웹페이지(GitHub Pages)** 로 다시 만든 것.
서버가 없어서 절대 잠들지 않는다. Streamlit 앱은 Pages 검증이 끝날 때까지 **그대로 유지**한다(`main_app.py`는 건드리지 않음).

- 사이트 주소: `https://gjdnddd.github.io/SF-STOCK/`
- 소스: `pages/` (index.html, style.css, app.js) — 데이터 없는 순수 화면 코드
- 데이터 변환: `scripts/build_pages.py` — `종목_히스토리.xlsx` + `theme_list.txt` → JSON
- 배포: `.github/workflows/pages.yml` — GitHub Actions가 자동 실행

## 데이터 흐름 (엑셀 갱신 쪽이 알아야 할 것 전부)

```
[엑셀 갱신] 종목_히스토리.xlsx 수정 (OneDrive "2. 노후준비\1.2. 주식\2. 유목민\종목 히스토리\")
   └─ github_push.py 가 GitHub Contents API(PUT)로 xlsx 1개만 업로드 → main에 커밋 생성
        │      (git clone/git push 를 쓰지 않는다. 커밋 메시지: "종목_히스토리 업데이트 - YYYY-MM-DD HH:MM")
        ├─▶ GitHub Actions: build_pages.py 로 JSON 생성 → Pages 자동 재배포   (신규)
        ├─▶ Streamlit Cloud: main 변경 감지 → 앱 재배포                      (기존, 당분간 유지)
        └─▶ 리눅스 서버: 매일 06:00 git pull → BigQuery 적재                 (기존, nextmove/run_db_sync.sh)
```

**엑셀 갱신 쪽이 할 일은 기존과 같다: `github_push.py` 로 `종목_히스토리.xlsx` 를 올리는 것뿐. 바꿀 것 없음.**
업로드가 API 방식(파일 sha 기준)이라 이 레포에 다른 파일이 커밋돼도 충돌하지 않으며, 그 PC에서 `git pull` 같은 작업은 필요 없다.
JSON은 올릴 필요 없고 올리면 안 된다. JSON은 `_site/` 에만 생기고 `.gitignore` 로 제외되어 있으며 Actions가 배포 때마다 새로 만든다.

## 체크리스트

1. `github_push.py` 의 업로드 대상(`REPO=gjdnddd/SF-STOCK`, `GITHUB_FILE=종목_히스토리.xlsx`)과 커밋 메시지 형식을 바꾸지 말 것.
   (다른 경로/이름으로 올리면 Pages·Streamlit·리눅스 서버 모두 갱신되지 않는다.)
   토큰이 파일에 평문으로 들어 있으니 화면·로그·채팅에 출력하거나 다른 곳에 복사하지 말 것.
2. `종목_히스토리.xlsx` 의 **컬럼 이름을 바꾸지 말 것.** 빌드 스크립트가 아래 컬럼을 이름으로 찾는다.
   `종목명, 코어테마, 전체테마, 대장이력, 기사, 키워드요약, 기사본문, K스윙 정리`
   (기존 Streamlit 앱도 같은 이름을 쓰므로 변경하면 둘 다 깨진다.) 컬럼이 없으면 Actions 빌드가 **실패하고 배포를 하지 않는다**(기존 사이트는 그대로 남음).
3. 테마 키워드 추가: 웹 화면에서는 추가할 수 없다(정적 페이지라 서버 저장 불가). `theme_list.txt` 에 한 줄 추가 후 이 레포에 push 하면 자동 반영된다.
   (Streamlit 사이드바의 "테마 리스트 추가"는 Streamlit 앱에서만 계속 동작.)
4. 업로드 후 **1~2분 뒤** 사이트 좌측 하단 "데이터 갱신: 날짜" 가 바뀌었는지 보면 반영 여부를 알 수 있다.
   실패 시 Actions 탭(https://github.com/gjdnddd/SF-STOCK/actions)에서 "Deploy GitHub Pages" 로그 확인.

## 최초 1회 설정 (완료됨 — 2026-09-21, 참고용)

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
- 검색 규칙은 기존 `main_app.py` 를 옮긴 것(초성 검색, 완전일치 시 숫자·기호 제거).
- **정렬 규칙**(코어테마 기준, 큰 게 위): 검색어 뒤 숫자 → 같으면 `-` 뒤 숫자 (예: `SMR10-8` > `SMR10-2` > `SMR10` > `SMR5-3` > `SMR5-1`).
  대소문자는 구분하지 않고(`smr` 입력해도 `SMR5` 인식), 완전히 같으면 엑셀 순서를 유지한다.
  Streamlit(`main_app.py`)은 대소문자를 구분하고 `-` 뒤 숫자를 보지 않아 순서가 다르다.
- 종목 상세의 "종목 선택"은 입력창이다. 종목명 일부 또는 초성(예: `ㅅㅅㅈㅈ`)으로 검색, ↑↓ Enter 로 선택.
- Streamlit과 다른 점: 빈 셀이 `nan` 으로 매칭되지 않고 "정보 없음"으로 표시됨, 검색어 입력 시 Enter 없이 바로 반영.

## 데이터 구조 (`_site/data/`)

| 파일 | 내용 | 로딩 시점 |
|---|---|---|
| `light.json` | 종목명, 코어테마, 전체테마, 대장이력 (약 0.4MB) | 페이지 열 때 |
| `article.json` `keyword.json` `body.json` `kswing.json` | 무거운 텍스트 컬럼 (body 9MB 등) | 해당 컬럼을 검색 범위에 넣거나 상세 탭을 열 때 |
| `themes.json` | `theme_list.txt` 목록 | 페이지 열 때 |

## 문제 해결

- **Actions 실패**: Actions 탭에서 로그 확인. 대부분 xlsx 컬럼명 변경 또는 파일 깨짐(행 100개 미만이면 일부러 실패시킴).
- **사이트가 안 바뀜**: xlsx 가 아니라 다른 파일만 push 했을 수 있다(트리거는 `종목_히스토리.xlsx`, `theme_list.txt`, `pages/**`, `scripts/build_pages.py`). Actions 탭에서 수동 실행 가능.
- **업로드가 안 됨**: `github_push.py` 의 토큰 만료/권한, 인터넷 연결, 업로드 대상 경로를 확인(체크리스트 1번).
