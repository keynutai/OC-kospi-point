# OC-kospi-point Context Summary

> 최종 업데이트: 2026-09-10 (목) / 브랜치: main / 원격: https://github.com/keynutai/OC-kospi-point

## 1. 프로젝트 목적
- 대한민국 코스피(^KS11) 일별 마감가를 수집해 **텍스트(.txt) + 인터랙티브 HTML(.html/index.html)** 로 저장
- GitHub Pages(https://keynutai.github.io/OC-kospi-point/)로 웹 공개
- OpenCode 바이브코딩 첫 경험 프로젝트

## 2. 핵심 요구사항
- **수집 기간**: 2026-01-01 ~ 오늘(`date.today()`)
- **데이터 소스 이중화**: `FinanceDataReader`(티커 `KS11`, end 포함) + `yfinance`(티커 `^KS11`, end 미포함) 동시 수집 후 유효 데이터 기준 최신 선택
- **유효성 필터**: `Close`가 `NaN/0`인 placeholder 행은 제외 (자정 직후 공급사 미갱신 대응)
- **날짜 비교**: 각 소스 `dropna(subset=["Close"])` 후 `_last_valid().index[-1]` 비교
- **END_DATE 처리**: 표시/저장용 `END_DATE = today`, yfinance 전용 `END_DATE_YF = today+1` 분리. `fetch_and_compare_data` 내부에서 자동 보정
- **첫날 전일대비 정확 계산**: 2025-12-01~12-31 조회 후 마지막 거래일(예: 2025-12-30)을 `prev_row`로 concat, `pct_change`/`diff` 계산
- **표시 형식**: 날짜 `YYYY-MM-DD (요일)` (월~일), `등락(pt)`(일반 텍스트) / `등락(%)`(▲ 빨강, ▼ 파랑) 분리, 월별 구분선, 최신순/과거순 정렬 버튼, 다크/라이트 테마
- **통계 카드**: 최고가/최저가/평균/최근가
- **실행 환경**: `kospi_venv` 가상환경, `run_kospi.command`(macOS 더블클릭), `pip install finance-datareader yfinance pandas`
- **운영 원칙**: `AGENTS.md` 기준 한국어 사용, 코딩 후 테스트/커밋·푸시는 사용자 확인 후 진행

## 3. 파일 구성
- `kospi_fetch.py`: 메인 수집/가공/저장 로직 (735→767줄)
- `kospi_closing_prices.txt` / `kospi_closing_prices.html` / `index.html`: 생성 결과물
- `run_kospi.command`: Finder 더블클릭 실행기
- `kospi_venv/`: 가상환경 (finance-datareader 0.9.202, yfinance 1.7.0, pandas 3.0.5)
- `README.md`: 기능/실행법/Changelog 문서
- `.gitignore`, `.DS_Store` 등

## 4. 핵심 로직 요약 (`kospi_fetch.py`)
- **상수**: `TICKER="KS11"`, `START_DATE="2026-01-01"`, `END_DATE=today`, `END_DATE_YF=today+1`
- `fetch_kospi_data_fdr(ticker,start,end)`: `fdr.DataReader` → `Close` 수치화 → `dropna(subset=["Close"])` & `!=0` → `sort_index()`
- `fetch_kospi_data_yf(ticker,start,end)`: `yf.download("^"+ticker)` → MultiIndex 평탄화 → 동일 NaN/0 필터 → `sort_index()`
- `fetch_and_compare_data(ticker,start,end)`: `end_fdr=end`, `end_yf=end+1`로 각각 호출 → `_last_valid()` 비교 → 최신 유효 df 반환
- `main()`: 2025 마지막 거래일 조회 → 본 데이터 조회 → `Close`만 추출 → `prev_row` concat → `Pct_Change`/`Point_Change` 계산 → `iloc[1:]` + `dropna(subset=["Close"])` → `save_to_file`/`save_to_html`×2 + 콘솔 통계
- `save_to_file`/`save_to_html`: 월별 구분, 요일 포함, 등락 컬럼 분리, 정렬용 `rowsAsc`/`rowsDesc` 생성

## 5. 작업 내역 (Changelog)
- **2026-09-10 (목) 데이터 소스 이중화**: FDR+yfinance 비교 선택, 티커 자동변환, MultiIndex 평탄화, `sort_index` 추가 (커밋 `b427429`)
- **2026-09-10 (목) 자정 NaN 버그 수정 (미커밋)**: `END_DATE` 분리, NaN/0 필터, `_last_valid` 비교, 최종 `dropna(subset=["Close"])`로 변경 — 로컬에만 적용, 사용자 요청으로 푸시 보류
- **2026-09-06 (일) 요일 추가**: `YYYY-MM-DD (요일)` 형식으로 txt/html/콘솔 전체 변경 (커밋 `bfaa78d`)
- **2026-09-04 (금) FDR 교체**: yfinance 지연으로 FinanceDataReader로 교체 (커밋 `1585d61`)
- **2026-08-30 (일) NaN 처리**: `dropna()`로 불완전 행 제외
- **2026-08-16 (일) 전일대비 개편**: `Point_Change` 분리, 2열 구조로 변경

## 6. 해결된 이슈
- **자정 직후 9/9 NaN 문제**: 공급사 갱신 지연으로 00시에 `NaN` placeholder 생성 → 유효 필터 추가로 해결. 재현 테스트 4개 PASS, `py_compile` ok, 실제 실행 168건(마지막 2026-09-08) 정상

## 7. 실행 방법
```bash
# A. Finder 더블클릭
open run_kospi.command

# B. 터미널
git clone https://github.com/keynutai/OC-kospi-point.git
cd OC-kospi-point
python3 -m venv kospi_venv
source kospi_venv/bin/activate
pip install finance-datareader yfinance pandas
python kospi_fetch.py
# 또는
./kospi_venv/bin/python kospi_fetch.py
```

## 8. Git 상태 (2026-09-10 04:22 이후)
- 마지막 푸시: `b427429 feat: dual data source (FDR KS11 + yfinance ^KS11) with latest-date selection` → `origin/main`
- 로컬 미커밋 변경: `kospi_fetch.py`(자정 버그 수정), `kospi_closing_prices.*`, `index.html`(재실행 결과) — 사용자 요청으로 푸시 보류
- `README.md`는 `b427429`에 이중화 내용 반영 완료, 자정 수정 내용은 미반영

## 9. 다음 단계 (선택)
- 자정 수정 커밋/푸시 및 `README.md` Changelog에 2026-09-10 자정 수정 항목 추가
- GitHub Pages 배포 확인
- 장 마감 후(18시 이후) 실행 권장 문구 문서화
