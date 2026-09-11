"""
코스피 지수 일별 마감가 수집 프로그램
- 기간: 2026년 1월 1일 ~ 오늘
- 데이터 소스: FinanceDataReader (KS11) + yfinance (^KS11) 이중 수집 후 유효 데이터 기준 최신 선택
- 저장 형식: 텍스트 파일 (kospi_closing_prices.txt)
            + HTML 파일 (kospi_closing_prices.html, index.html)
"""

try:
    import FinanceDataReader as fdr
except Exception as e:
    fdr = None
    print(f"⚠️ FinanceDataReader import failed: {e}")

try:
    import yfinance as yf
except Exception as e:
    yf = None
    print(f"⚠️ yfinance import failed: {e}")

import pandas as pd
from datetime import date, datetime, timedelta
import os

# ── 설정 ────────────────────────────────────────────────────
TICKER           = "KS11"
START_DATE       = "2026-01-01"
END_DATE         = date.today().strftime("%Y-%m-%d")                          # 화면 표시/저장용 (오늘까지)
END_DATE_YF      = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")    # yfinance는 end 미포함이라 +1일
OUTPUT_FILE      = "kospi_closing_prices.txt"
OUTPUT_FILE_HTML = "kospi_closing_prices.html"
OUTPUT_FILE_INDEX= "index.html"                 # GitHub Pages 기본 인덱스 파일
# ────────────────────────────────────────────────────────────


def fetch_kospi_data_fdr(ticker, start, end):
    """FinanceDataReader에서 코스피 일별 데이터를 가져옵니다. (NaN 마감가 행 자동 제외)"""
    print(f"📡 FinanceDataReader에서 코스피 데이터 다운로드 중... ({start} ~ {end})")
    if fdr is None:
        raise RuntimeError("FinanceDataReader 라이브러리가 설치되어 있지 않습니다.")
    df = fdr.DataReader(ticker, start=start, end=end)
    if df.empty:
        return pd.DataFrame()
    
    # 열 이름 표준화
    df = df.rename(columns={'Close': 'Close', 'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Volume': 'Volume'})
    # 자정 직후 등 공급사 지연으로 생기는 NaN/0 placeholder 제거
    if 'Close' in df.columns:
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        before = len(df)
        df = df.dropna(subset=['Close'])
        df = df[df['Close'] != 0]
        if len(df) != before:
            print(f"   ↳ FDR NaN/0 행 {before - len(df)}건 제외")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df

def fetch_kospi_data_yf(ticker, start, end):
    """yfinance에서 코스피 일별 데이터를 가져옵니다. (NaN 마감가 행 자동 제외)"""
    print(f"📡 yfinance에서 코스피 데이터 다운로드 중... ({start} ~ {end})")
    if yf is None:
        raise RuntimeError("yfinance 라이브러리가 설치되어 있지 않습니다.")
    
    symbol = f"^{ticker}" if not ticker.startswith('^') else ticker
    df = yf.download(symbol, start=start, end=end, progress=False)
    
    if df.empty:
        return pd.DataFrame()
    
    # yfinance의 MultiIndex 또는 다양한 열 이름을 표준화
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    df = df.rename(columns={
        'Open': 'Open',
        'High': 'High', 
        'Low': 'Low',
        'Close': 'Close',
        'Volume': 'Volume'
    })
    # yfinance는 가끔 Date가 인덱스이거나 컬럼이므로 확실히 정렬
    df.index = pd.to_datetime(df.index)
    # Close 컬럼만 있으면 되므로 필수 컬럼 확인 후 반환 (Close 필수)
    if 'Close' not in df.columns:
        raise ValueError("yfinance 데이터에 Close 컬럼이 없습니다.")
    # 자정 직후 등 공급사 지연으로 생기는 NaN/0 placeholder 제거
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    before = len(df)
    df = df.dropna(subset=['Close'])
    df = df[df['Close'] != 0]
    if len(df) != before:
        print(f"   ↳ yfinance NaN/0 행 {before - len(df)}건 제외")
    df = df.sort_index()
    return df

def fetch_and_compare_data(ticker, start, end):
    """FinanceDataReader와 yfinance에서 데이터를 가져와서 비교하고 더 최신(유효) 데이터를 선택합니다."""
    print("📡 두 데이터 소스에서 데이터를 가져오는 중...")
    
    if fdr is None and yf is None:
        raise RuntimeError("데이터를 가져올 수 있는 라이브러리(FinanceDataReader, yfinance)가 모두 없습니다.")
    
    # yfinance는 end 미포함이므로 +1일 보정, FDR은 end 포함이라 그대로
    try:
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        end_yf = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        end_yf = end
    end_fdr = end
    
    df_fdr = None
    df_yf = None
    
    if fdr is not None:
        try:
            df_fdr = fetch_kospi_data_fdr(ticker, start, end_fdr)
        except Exception as e:
            print(f"⚠️ FinanceDataReader 수집 중 오류 발생: {e}")
            
    if yf is not None:
        try:
            df_yf = fetch_kospi_data_yf(ticker, start, end_yf)
        except Exception as e:
            print(f"⚠️ yfinance 수집 중 오류 발생: {e}")
            
    # 유효 데이터(Close NaN/0 제외) 기준 마지막 날짜 비교 - 자정 placeholder 무시
    def _last_valid(df):
        if df is None or df.empty:
            return None
        # 이미 fetch_*에서 NaN/0 제거됐지만 방어적으로 재필터
        valid = df.dropna(subset=['Close'])
        valid = valid[pd.to_numeric(valid['Close'], errors='coerce').notna()]
        valid = valid[valid['Close'] != 0]
        return valid.index[-1] if not valid.empty else None

    last_date_fdr = _last_valid(df_fdr)
    last_date_yf = _last_valid(df_yf)
    
    print(f"   FinanceDataReader 마지막 날짜: {last_date_fdr}")
    print(f"   yfinance 마지막 날짜: {last_date_yf}")
    
    if last_date_fdr and last_date_yf:
        if last_date_fdr >= last_date_yf:
            print("   📈 FinanceDataReader 데이터가 더 최신이거나 같습니다. 선택합니다.")
            return df_fdr
        else:
            print("   📈 yfinance 데이터가 더 최신입니다. 선택합니다.")
            return df_yf
    elif last_date_fdr:
        print("   📈 FinanceDataReader 데이터가 유일합니다. 선택합니다.")
        return df_fdr
    elif last_date_yf:
        print("   📈 yfinance 데이터가 유일합니다. 선택합니다.")
        return df_yf
    else:
        raise ValueError("두 데이터 소스 모두에서 데이터를 가져올 수 없습니다.")


# ──────────────────────────────────────────────────────────────
#  텍스트 저장
# ──────────────────────────────────────────────────────────────
def save_to_file(df, output_path):
    """데이터프레임을 텍스트 파일로 저장합니다."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 50 + "\n")
        f.write("  대한민국 코스피 지수 일별 마감가\n")
        f.write(f"  수집 기간 : {START_DATE} ~ {END_DATE}\n")
        f.write(f"  생성 일시 : {now_str}\n")
        f.write(f"  데이터 건수: {len(df)}건\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"{'날짜':<14}{'마감가 (KRW)':>15}{'등락(pt)':>10}{'등락(%)':>10}\n")
        f.write("-" * 49 + "\n")

        current_month = None
        for idx, row in df.iterrows():
            date_str  = idx.strftime("%Y-%m-%d") + f" ({['월', '화', '수', '목', '금', '토', '일'][idx.weekday()]})"
            month_key = (idx.year, idx.month)
            if month_key != current_month:
                if current_month is not None:
                    f.write("\n")
                label = f"  {idx.year}년 {idx.month:02d}월  "
                f.write(f"{'─' * 14}{label}{'─' * (28 - len(label))}\n")
                current_month = month_key
            close_val = float(row["Close"])
            pct       = row["Pct_Change"]
            point     = row["Point_Change"]
            pct_str   = "-" if pct != pct else f"{pct:+.2f}%"
            point_str = "-" if point != point else f"{point:+.2f}"
            f.write(f"{date_str:<14}{close_val:>15,.2f}{point_str:>10}{pct_str:>10}\n")

    print(f"✅ 저장 완료: {output_path}  ({len(df)}건)")


# ──────────────────────────────────────────────────────────────
#  HTML 저장
# ──────────────────────────────────────────────────────────────
def save_to_html(df, output_path, last_2025_date, last_2025):
    """데이터프레임을 스타일링된 HTML 파일로 저장합니다."""
    now_str      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    close_series = df["Close"]

    # ── 월별 테이블 행 생성 (과거순 asc / 최신순 desc 준비) ──
    MONTH_KO = ["", "1월", "2월", "3월", "4월", "5월", "6월",
                "7월", "8월", "9월", "10월", "11월", "12월"]

    def build_rows(data_df):
        rows = []
        current_month = None
        for idx, row in data_df.iterrows():
            month_key = (idx.year, idx.month)
            if month_key != current_month:
                label = f"{idx.year}년 {MONTH_KO[idx.month]}"
                rows.append(
                    f'<tr class="month-sep"><td colspan="4">📅 {label}</td></tr>'
                )
                current_month = month_key

            date_str  = idx.strftime("%Y-%m-%d") + f" ({['월', '화', '수', '목', '금', '토', '일'][idx.weekday()]})"
            close_val = float(row["Close"])
            pct       = row["Pct_Change"]
            point     = row["Point_Change"]

            point_cell = "—" if point != point else f"{point:+.2f}"

            if pct != pct:
                pct_cell = '<span class="flat">—</span>'
            elif pct > 0:
                pct_cell = f'<span class="up">▲ {pct:+.2f}%</span>'
            elif pct < 0:
                pct_cell = f'<span class="down">▼ {pct:+.2f}%</span>'
            else:
                pct_cell = '<span class="flat">0.00%</span>'

            rows.append(
                f'<tr>'
                f'<td class="date">{date_str}</td>'
                f'<td class="close">{close_val:,.2f}</td>'
                f'<td>{point_cell}</td>'
                f'<td class="pct">{pct_cell}</td>'
                f'</tr>'
            )
        return "\n        ".join(rows)

    rows_asc_html  = build_rows(df)
    rows_desc_html = build_rows(df.iloc[::-1])

    # ── 통계 값 미리 계산 ──
    val_high   = f"{close_series.max():,.0f}"
    val_low    = f"{close_series.min():,.0f}"
    val_avg    = f"{close_series.mean():,.0f}"
    val_recent = f"{close_series.iloc[-1]:,.0f}"
    val_last   = f"{last_2025:,.2f}"

    # ── HTML 생성 ──
    html = """\
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>코스피 지수 일별 마감가 (2026)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', sans-serif;
      background: #0d1117;
      color: #e6edf3;
      min-height: 100vh;
      padding: 2.5rem 1rem;
      transition: background-color 0.3s, color 0.3s;
    }
    .container { max-width: 780px; margin: 0 auto; }
    .header-card {
      background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
      border: 1px solid #30363d;
      border-radius: 16px;
      padding: 2rem 2.5rem;
      margin-bottom: 1.2rem;
      position: relative;
      overflow: hidden;
    }

    /* Light theme styles */
    body.light-theme {
      background: #f6f8fa;
      color: #24292f;
    }

    body.light-theme .header-card {
      background: linear-gradient(135deg, #ffffff 0%, #f6f8fa 100%);
      border: 1px solid #d1d5da;
    }

    body.light-theme .stat-card {
      background: #ffffff;
      border: 1px solid #d1d5da;
    }

    body.light-theme .table-wrapper {
      background: #ffffff;
      border: 1px solid #d1d5da;
    }

    body.light-theme .header-card h1 {
      color: #0969da;
    }

    body.light-theme .meta-grid {
      color: #656d76;
    }

    body.light-theme .meta-grid strong {
      color: #24292f;
    }

    body.light-theme .stat-card.high .stat-value {
      color: #cf222e;
    }

    body.light-theme .stat-card.low .stat-value {
      color: #0969da;
    }

    body.light-theme .stat-card.avg .stat-value {
      color: #24292f;
    }

    body.light-theme .stat-card.last .stat-value {
      color: #24292f;
    }

    body.light-theme .sort-buttons {
      background: #ffffff;
      border: 1px solid #d1d5da;
    }

    body.light-theme .sort-btn {
      color: #656d76;
    }

    body.light-theme .sort-btn:hover {
      color: #24292f;
    }

    body.light-theme .sort-btn.active {
      background: #0969da;
      color: #ffffff;
    }

    body.light-theme .table-wrapper {
      background: #ffffff;
      border: 1px solid #d1d5da;
    }

    body.light-theme thead th {
      background: #f6f8fa;
      color: #656d76;
    }

    body.light-theme tbody tr:hover:not(.month-sep) {
      background: #f6f8fa;
    }

    body.light-theme tbody tr {
      border-top: 1px solid #d1d5da;
    }

    body.light-theme tr.month-sep td {
      background: #f6f8fa;
      color: #24292f;
      border-top: 2px solid #d1d5da;
    }

    body.light-theme tr.month-sep {
      border-top: 1px solid #a8adb0;
    }

    body.light-theme td.date {
      color: #656d76;
    }

    body.light-theme td.close {
      color: #24292f;
    }

    body.light-theme .up {
      color: #cf222e;
    }

    body.light-theme .down {
      color: #0969da;
    }

    body.light-theme .flat {
      color: #656d76;
    }

    body.light-theme .footer {
      color: #8c949d;
    }

    body.light-theme .stat-card:hover {
      border-color: #0969da;
    }
    .header-card::after {
      content: '';
      position: absolute;
      top: -80px; right: -80px;
      width: 220px; height: 220px;
      background: radial-gradient(circle, rgba(88,166,255,0.10) 0%, transparent 70%);
      pointer-events: none;
    }
    .header-card h1 {
      font-size: 1.55rem;
      font-weight: 700;
      color: #58a6ff;
      letter-spacing: -0.02em;
      margin-bottom: 1rem;
    }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 0.5rem 2rem;
      font-size: 0.85rem;
      color: #8b949e;
    }
    .meta-grid div { white-space: nowrap; }
    .meta-grid strong { color: #e6edf3; font-weight: 500; }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.75rem;
      margin-bottom: 1.2rem;
    }
    .stat-card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 12px;
      padding: 1rem 0.8rem;
      text-align: center;
      transition: border-color 0.2s;
    }
    .stat-card:hover { border-color: #58a6ff; }
    .stat-label {
      font-size: 0.68rem;
      color: #8b949e;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      margin-bottom: 0.4rem;
    }
    .stat-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.05rem;
      font-weight: 600;
    }
    .stat-card.high .stat-value { color: #f85149; }
    .stat-card.low  .stat-value { color: #58a6ff; }
    .stat-card.avg  .stat-value { color: #e6edf3; }
    .stat-card.last .stat-value { color: #e6edf3; }

    /* ── 정렬 컨트롤 바 ── */
    .controls-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.8rem;
      padding: 0 0.4rem;
    }
    .controls-title {
      font-size: 0.85rem;
      color: #8b949e;
      font-weight: 500;
    }
    .sort-buttons {
      display: flex;
      gap: 0.4rem;
      background: #161b22;
      padding: 4px;
      border: 1px solid #30363d;
      border-radius: 10px;
    }
    .sort-btn {
      background: transparent;
      border: none;
      color: #8b949e;
      font-family: 'Inter', sans-serif;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 0.4rem 0.85rem;
      border-radius: 7px;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .sort-btn:hover {
      color: #e6edf3;
    }
    .sort-btn.active {
      background: #238636;
      color: #ffffff;
      box-shadow: 0 2px 5px rgba(0,0,0,0.3);
    }

    .table-wrapper {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 16px;
      overflow: hidden;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }
    thead th {
      background: #1c2333;
      color: #8b949e;
      font-weight: 600;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      padding: 0.9rem 1.4rem;
      text-align: right;
    }
    thead th:first-child { text-align: left; }
    tbody tr {
      border-top: 1px solid #21262d;
      transition: background 0.12s;
    }
    tbody tr:hover:not(.month-sep) { background: #1c2333; }
    tr.month-sep td {
      background: #1c2333;
      color: #ffffff;
      text-align: center;
      font-size: 0.8rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      padding: 0.6rem 1.4rem;
      border-top: 2px solid #30363d;
    }
    td {
      padding: 0.6rem 1.4rem;
      font-family: 'JetBrains Mono', monospace;
      text-align: right;
    }
    td.date  { text-align: left; color: #8b949e; font-size: 0.82rem; }
    td.close { color: #e6edf3; }
    td.pct   { min-width: 110px; }
    .up   { color: #f85149; font-weight: 600; }
    .down { color: #4a9eff; font-weight: 600; }
    .flat { color: #8b949e; }
    .footer {
      text-align: center;
      margin-top: 1.2rem;
      font-size: 0.73rem;
      color: #484f58;
    }
    @media (max-width: 580px) {
      .stats-grid { grid-template-columns: repeat(2, 1fr); }
      .header-card { padding: 1.3rem 1.5rem; }
      thead th, td { padding-left: 0.8rem; padding-right: 0.8rem; }
    }
  </style>
</head>
<body>
<div class="container">

  <div class="header-card">
    <h1>📊 코스피 지수 일별 마감가</h1>
    <div class="meta-grid">
      <div>수집 기간 &nbsp;<strong>%%START_DATE%% ~ %%END_DATE%%</strong></div>
      <div>데이터 건수 &nbsp;<strong>%%TOTAL%%건</strong></div>
      <div>전일 기준일 &nbsp;<strong>%%LAST_DATE%% (%%LAST_VAL%% pt)</strong></div>
      <div>생성 일시 &nbsp;<strong>%%NOW%%</strong></div>
    </div>
  </div>

  <div class="stats-grid">
    <div class="stat-card high">
      <div class="stat-label">최고가</div>
      <div class="stat-value">%%HIGH%%</div>
    </div>
    <div class="stat-card low">
      <div class="stat-label">최저가</div>
      <div class="stat-value">%%LOW%%</div>
    </div>
    <div class="stat-card avg">
      <div class="stat-label">평 균</div>
      <div class="stat-value">%%AVG%%</div>
    </div>
    <div class="stat-card last">
      <div class="stat-label">최근가</div>
      <div class="stat-value">%%RECENT%%</div>
    </div>
  </div>

  <div class="controls-bar">
    <div class="controls-title">📈 일별 거래 내역</div>
    <div class="sort-buttons">
      <button id="btnDesc" class="sort-btn active" onclick="setSortOrder('desc')">⏳ 최신순</button>
      <button id="btnAsc" class="sort-btn" onclick="setSortOrder('asc')">⌛ 과거순</button>
      <button id="themeToggle" class="sort-btn" onclick="toggleTheme()">🌙 어둡게</button>
    </div>
  </div>

  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>날짜</th>
          <th>마감가 (pt)</th>
          <th>등락 (pt)</th>
          <th>등락 (%)</th>
        </tr>
      </thead>
      <tbody id="tableBody">
        %%ROWS_DESC%%
      </tbody>
    </table>
  </div>

  <div class="footer">
    데이터 출처: FinanceDataReader / yfinance &nbsp;·&nbsp; 자동 생성됨
  </div>

</div>

<script>
  const rowsAsc = `%%ROWS_ASC%%`;
  const rowsDesc = `%%ROWS_DESC%%`;

  function setSortOrder(order) {
    const tableBody = document.getElementById('tableBody');
    const btnAsc = document.getElementById('btnAsc');
    const btnDesc = document.getElementById('btnDesc');

    if (order === 'desc') {
      tableBody.innerHTML = rowsDesc;
      btnDesc.classList.add('active');
      btnAsc.classList.remove('active');
    } else {
      tableBody.innerHTML = rowsAsc;
      btnAsc.classList.add('active');
      btnDesc.classList.remove('active');
    }
  }

  function toggleTheme() {
    const body = document.body;
    const themeButton = document.getElementById('themeToggle');

    // Toggle the theme class
    body.classList.toggle('light-theme');

    // Save preference to localStorage
    if (body.classList.contains('light-theme')) {
      localStorage.setItem('theme', 'light');
      themeButton.textContent = '☀️ 밝게';
    } else {
      localStorage.setItem('theme', 'dark');
      themeButton.textContent = '🌙 어둡게';
    }
  }

  // Check for saved theme preference or default to dark theme
  document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
      document.body.classList.add('light-theme');
      document.getElementById('themeToggle').textContent = '☀️ 밝게';
    }
  });
</script>

</body>
</html>
"""

    # 플레이스홀더를 실제 값으로 치환
    html = (
        html
        .replace("%%START_DATE%%", START_DATE)
        .replace("%%END_DATE%%",   END_DATE)
        .replace("%%TOTAL%%",      str(len(df)))
        .replace("%%NOW%%",        now_str)
        .replace("%%LAST_DATE%%",  last_2025_date)
        .replace("%%LAST_VAL%%",   val_last)
        .replace("%%HIGH%%",       val_high)
        .replace("%%LOW%%",        val_low)
        .replace("%%AVG%%",        val_avg)
        .replace("%%RECENT%%",     val_recent)
        .replace("%%ROWS_ASC%%",   rows_asc_html)
        .replace("%%ROWS_DESC%%",  rows_desc_html)
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML 저장 완료: {output_path}  ({len(df)}건)")


# ──────────────────────────────────────────────────────────────
#  메인
# ──────────────────────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  코스피 마감가 수집 프로그램")
    print("=" * 50)

    import pandas as pd

    # 2025년 마지막 거래일 마감가 조회 (첫날 전일대비 계산용)
    print("📡 2025년 마지막 거래일 데이터 조회 중...")
    df_prev  = fetch_and_compare_data(TICKER, "2025-12-01", "2025-12-31")
    prev_col = df_prev["Close"]
    if isinstance(prev_col, pd.DataFrame):
        prev_col = prev_col.iloc[:, 0]
    
    last_2025 = float(prev_col.iloc[-1])
    last_2025_raw = prev_col.index[-1].strftime("%Y-%m-%d")
    last_2025_date = last_2025_raw + f" ({['월', '화', '수', '목', '금', '토', '일'][prev_col.index[-1].weekday()]})"
    print(f"   └ 2025년 마지막 거래일: {last_2025_date}  종가: {last_2025:,.2f} pt")

    # 본 데이터 수집 (2026-01-01 ~ 오늘)
    df = fetch_and_compare_data(TICKER, START_DATE, END_DATE)

    close_col = df["Close"]
    if isinstance(close_col, pd.DataFrame):
        close_col = close_col.iloc[:, 0]
    df = close_col.to_frame(name="Close")

    # 2025년 마지막 거래일을 임시로 앞에 붙여 첫 행 전일대비 계산
    prev_row = pd.DataFrame(
        {"Close": [last_2025]},
        index=pd.DatetimeIndex([prev_col.index[-1]])
    )
    df = pd.concat([prev_row, df])
    df["Pct_Change"] = df["Close"].pct_change() * 100
    df["Point_Change"] = df["Close"].diff()
    df = df.iloc[1:]
    # 자정 placeholder 등으로 Close가 NaN/0인 행이 생기면 제거하되, 정상 등락 계산은 유지
    before = len(df)
    df = df.dropna(subset=["Close"])
    df = df[pd.to_numeric(df["Close"], errors="coerce").notna()]
    df = df[df["Close"] != 0]
    if len(df) != before:
        print(f"   ↳ 최종 NaN/0 행 {before - len(df)}건 제외 (자정 직후 미갱신 데이터)")

    base = os.path.dirname(os.path.abspath(__file__))

    # 텍스트 저장
    save_to_file(df, os.path.join(base, OUTPUT_FILE))

    # HTML 저장
    save_to_html(df, os.path.join(base, OUTPUT_FILE_HTML), last_2025_date, last_2025)
    save_to_html(df, os.path.join(base, OUTPUT_FILE_INDEX), last_2025_date, last_2025)

    # 통계 출력
    close_series = df["Close"]
    print(f"\n📊 기간 내 통계")
    print(f"   최고가 : {close_series.max():,.2f} pt")
    print(f"   최저가 : {close_series.min():,.2f} pt")
    print(f"   평  균 : {close_series.mean():,.2f} pt")
    print(f"   최근가 : {close_series.iloc[-1]:,.2f} pt  ({df.index[-1].strftime('%Y-%m-%d')} ({['월', '화', '수', '목', '금', '토', '일'][df.index[-1].weekday()]}))")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ {e}")
