from flask import Flask, request, render_template_string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import os
import json
from pathlib import Path

app = Flask(__name__)

# ====== 設定 ======
SPREADSHEET_ID = '1PzrbtLu1e9vqfyvSPMOXKL2quMmmcQlpSD44be682ls'

# 使用通用的新版 Google API scopes（可讀寫；若只讀可把 spreadsheets 改成 *.readonly）
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly'
]

# 以檔案所在資料夾為基準（絕對路徑），避免 CWD 變動
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = str(BASE_DIR / 'credentials.json')


# ====== 工具函式 ======
def has_credentials() -> bool:
    return os.path.exists(CREDENTIALS_FILE)


def gclient():
    """同時支援：
    1) Vercel/雲端：從環境變數 CREDENTIALS_JSON 讀取服務帳戶 JSON（建議）
    2) Replit 本地開發：讀取 Arete Select/credentials.json 檔案
    """
    # 優先用環境變數（Vercel 上用）
    creds_json = os.getenv("CREDENTIALS_JSON")
    if creds_json:
        try:
            info = json.loads(creds_json)
        except json.JSONDecodeError:
            raise RuntimeError(
                "CREDENTIALS_JSON 不是合法 JSON。請到 Vercel > Settings > Environment Variables "
                "把整份 credentials.json 內容『原樣、一行貼上』做為值。")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, SCOPES)
        return gspread.authorize(creds)

    # 退回用檔案（在 Replit 本地開發）
    if not has_credentials():
        raise FileNotFoundError(
            "找不到 credentials.json，請把服務帳戶金鑰上傳到『Arete Select』資料夾，或改用 CREDENTIALS_JSON 環境變數。"
        )
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENTIALS_FILE, SCOPES)
    return gspread.authorize(creds)


def is_type_col(colname: str) -> bool:
    colname = (colname or "").strip().lower().replace(" ", "")
    # 支援常見拼寫誤差
    return colname in ['type', 'tpye', 'typ', 'tpy', 'tpey']


def is_company_col(colname: str) -> bool:
    colname = (colname or "").strip().lower().replace(" ", "")
    # 支援多語/別名
    return colname in ['company', 'brand', '品牌', '公司']


def clean_cell(val) -> str:
    """移除看不見的控制字元/零寬字元/全形空白/斷行，再去前後空白。"""
    if val is None:
        return ''
    s = str(val)
    s = re.sub(
        r'[\u0000-\u001F\u007F-\u009F\u200B\u200C\u200D\u2028\u2029\u00A0\u3000]',
        '', s)
    s = s.replace('\n', '').replace('\r', '').strip()
    return s


# ====== 資料讀取 ======
def get_all_types():
    """蒐集所有工作表裡的 Type（去重，依出現順序）。"""
    types, seen = [], set()
    ss = gclient().open_by_key(SPREADSHEET_ID)
    for sheet in ss.worksheets():
        data = sheet.get_all_records()
        for row in data:
            for k in row.keys():
                if is_type_col(k):
                    tv = clean_cell(row[k])
                    if tv and tv not in seen:
                        seen.add(tv)
                        types.append(tv)
                    break
    return types


def get_results(keyword, categories):
    """
    跨所有分頁搜尋；只保留 Title & Video url 皆有值的列。
    關鍵字同時比對 Company、Title、以及其他欄位（不分大小寫）。
    """
    ss = gclient().open_by_key(SPREADSHEET_ID)
    results, all_fields = [], []
    keyword_for_cat = (keyword or '').strip()
    is_cat = keyword_for_cat in categories
    kw_lower = keyword_for_cat.lower()

    for sheet in ss.worksheets():
        data = sheet.get_all_records()
        for row in data:
            # 全空列跳過
            if all(not clean_cell(v) for v in row.values()):
                continue

            # 先清一份 row
            row_cp = {k: clean_cell(v) for k, v in row.items()}

            # 必須有 Title 與 Video url
            title_val = row_cp.get('Title', '')
            url_val = row_cp.get('Video url', '')
            if not title_val or not url_val:
                continue

            # 合併 Type 欄，統一為 'Type'
            type_val = None
            for k in list(row_cp.keys()):
                if is_type_col(k):
                    type_val = row_cp[k]
                    break
            if type_val is not None:
                row_cp['Type'] = type_val

            # Company 欄：支援 Company/品牌/公司/brand
            company_val = ''
            for k in list(row_cp.keys()):
                if is_company_col(k):
                    company_val = row_cp[k]
                    break
            row_cp['Company'] = company_val

            # 來源工作表
            row_cp['來源工作表'] = clean_cell(sheet.title)

            # 比對條件
            match_cat = (is_cat and type_val == keyword_for_cat)

            # 關鍵字：公司/標題/其他欄位（不分大小寫）
            if kw_lower:
                company_lower = company_val.lower()
                title_lower = title_val.lower()
                any_field_match = any(kw_lower in str(v).lower()
                                      for v in row_cp.values())
                match_kw = (kw_lower in company_lower) or (
                    kw_lower in title_lower) or any_field_match
            else:
                match_kw = False

            if match_cat or match_kw:
                # 移除其餘 Type 原欄名鍵，只保留 'Type'
                for delk in list(row_cp.keys()):
                    if is_type_col(delk) and delk != 'Type':
                        row_cp.pop(delk, None)

                results.append(row_cp)
                for k in row_cp.keys():
                    if k not in all_fields:
                        all_fields.append(k)

    return results, all_fields


# ====== 前端樣板 ======
TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>亞瑞特案例庫搜尋</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@500;700&display=swap" rel="stylesheet">
<style>
    body { font-family: 'Noto Sans TC', Arial, sans-serif; background: #121212; margin: 0; padding: 0 0 40px 0;}
    .main-wrap { max-width: 1220px; margin: 40px auto; background: #191919; border-radius: 16px; box-shadow: 0 2px 16px #2c2c2c; padding: 32px 32px 24px 32px;}
    .title-row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px;}
    h1 { font-size: 2.0rem; color: #ffd857; font-weight: 900; margin: 0; letter-spacing: 1px; }
    form { display: flex; align-items: center; gap: 8px; margin: 0;}
    input[type=text] {
        font-size: 1.05rem; padding: 10px 14px;
        border: 2px solid #2462ea; border-radius: 8px; min-width: 300px;
        background: #222; color: #fff; font-weight: 600;
    }
    button[type=submit] {
        background: #2462ea; color: #fff; border: none;
        padding: 10px 24px; border-radius: 8px; font-size: 1.05rem;
        cursor: pointer; font-weight: 900; box-shadow: 0 1px 8px #0003;
        transition: background 0.15s;
    }
    button[type=submit]:hover { background: #16397c; color: #fff;}
    .category-bar { margin: 16px 0 10px 0; display: flex; flex-wrap: wrap; gap: 10px;}
    .chip {
        background: #212940; color: #fff; border: 2px solid #2462ea; border-radius: 999px;
        padding: 7px 14px; font-size: 0.95rem; font-weight: 700; letter-spacing: 1px;
        cursor: pointer; transition: all 0.15s;
    }
    .chip:hover, .chip.selected { background: #2462ea; border-color: #ffd857; box-shadow: 0 2px 10px #2462ea77; }
    .filter-row { margin: 6px 0 0 0; display: flex; align-items: center; gap: 10px; color: #ffd857; }
    .filter-row label { font-weight: 800; }
    select[name=company_filter] {
        padding: 7px 14px; color: #222; font-size: 0.98rem; font-weight: 800; border: 2px solid #ffd857;
        background: #ffd857; border-radius: 8px;
    }
    .count-row { margin: 10px 0 8px 0; font-size: 1.0rem; color: #ffd857; display: flex; align-items: center; gap: 10px; font-weight: 700;}
    table { width: 100%; border-collapse: collapse; margin-top: 8px; background: #181818;}
    th, td { border: 1.4px solid #2462ea55; padding: 8px 10px; word-break: break-word; text-align: left; vertical-align: middle;}
    th { background: #ffd857; color: #222; font-weight: 900; letter-spacing: 1px;}
    td { color: #fff; font-size: 1.02rem; }
    tr:nth-child(even) td { background: #212940;}
    a { color: #ffd857; text-decoration: underline; }
    a:hover { color: #fff; background: #2462ea; }
    .no-result { color: #ffd857aa; font-size: 1.0rem; margin-top: 16px;}
    .searching { color: #ffd857; font-weight: 700; font-size: 1.05rem; padding: 14px 0; text-align:center;}
    th, td { min-width: 130px; }
    th:nth-child(4), td:nth-child(4) { min-width: 170px !important; white-space: normal !important; }
    @media (max-width: 700px) {
        .main-wrap { padding: 10px 1vw; }
        table, th, td { font-size: 0.95rem; }
        h1 { font-size: 1.4rem; }
        .title-row { flex-direction: column; gap: 8px;}
        th, td { padding: 6px 8px; }
    }
</style>
<script>
    function showLoading() {
        document.getElementById('searching-box').style.display = '';
        document.getElementById('result-box').style.display = 'none';
    }
    function hideLoading() {
        document.getElementById('searching-box').style.display = 'none';
        document.getElementById('result-box').style.display = '';
    }
    function quickSearch(val) {
        document.getElementById('keyword').value = val;
        document.getElementById('company_filter').value = '';
        showLoading();
        setTimeout(function(){document.getElementById('search-form').submit();}, 10);
    }
    window.onload = function(){ hideLoading(); }
</script>
</head>
<body>
<div class="main-wrap">
    <div class="title-row">
        <h1>亞瑞特案例庫搜尋</h1>
        <form id="search-form" method="get" action="/" onsubmit="showLoading()">
            <input type="text" id="keyword" name="keyword" placeholder="輸入關鍵字（同時比對 Company / Title）" value="{{ keyword or '' }}">
            <input type="hidden" id="company_filter" name="company_filter" value="{{ company_filter or '' }}">
            <button type="submit">搜尋</button>
        </form>
    </div>

    <div class="category-bar">
        {% for cat in categories %}
        <button type="button" class="chip {% if keyword == cat %}selected{% endif %}" onclick="quickSearch('{{cat}}')">{{cat}}</button>
        {% endfor %}
    </div>

    {% if keyword and companies %}
    <form method="get" id="company-form" class="filter-row" onsubmit="showLoading()">
        <input type="hidden" name="keyword" value="{{ keyword }}">
        <label for="company_select">篩選公司/品牌：</label>
        <select id="company_select" name="company_filter" onchange="document.getElementById('company-form').submit();">
            <option value="" {% if not company_filter %}selected{% endif %}>全部</option>
            {% for c in companies %}
                <option value="{{ c }}" {% if company_filter == c %}selected{% endif %}>{{ c }}</option>
            {% endfor %}
        </select>
    </form>
    {% endif %}

    <div id="searching-box" class="searching" style="display:none;">
        <span>搜尋中…請稍候</span>
    </div>

    <div id="result-box">
    {% if keyword %}
        {% if results %}
            <div class="count-row">🔍 條件：<b>{{ keyword }}</b>{% if company_filter %}｜公司：<b>{{ company_filter }}</b>{% endif %} ｜ 符合 <b>{{ results|length }}</b> 筆</div>
            <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        {% for col in columns %}
                        <th>{{ col }}</th>
                        {% endfor %}
                    </tr>
                </thead>
                <tbody>
                    {% for row in results %}
                    <tr>
                        {% for col in columns %}
                        <td>
                            {% set v = row.get(col, '') | string | trim | replace('\n','') | replace('\r','') %}
                            {% if v and v.startswith('http') %}
                                <a href="{{v}}" target="_blank">{{v}}</a>
                            {% else %}
                                {{v}}
                            {% endif %}
                        </td>
                        {% endfor %}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            </div>
        {% else %}
            <div class="no-result">❌ 找不到任何符合「{{keyword}}{% if company_filter %}／{{company_filter}}{% endif %}」的資料。</div>
        {% endif %}
    {% endif %}
    </div>
</div>
</body>
</html>
'''


# ====== 健康檢查（不碰 Google，方便快速判斷是否為憑證/權限問題）======
@app.route('/healthz', methods=['GET'])
def healthz():
    return "ok"


# ====== 路由 ======
@app.route('/', methods=['GET'])
def index():
    # 先嘗試載入類別；若 Google 連線/權限出錯，回友善提示
    try:
        categories = get_all_types()
    except Exception as e:
        msg = f"讀取 Google 試算表發生錯誤：{e}"
        help_html = f"""
        <h2 style="color:#ffd857">⚠️ 無法讀取資料</h2>
        <div style="color:#fff;line-height:1.6">
          <p>{msg}</p>
          <ol>
            <li>Vercel → Settings → Environment Variables：確認 <b>CREDENTIALS_JSON</b> 已設定，值為 <b>完整且合法的 JSON</b>（不要加引號、不要 json.dumps）。</li>
            <li>到 Google 試算表（ID：{SPREADSHEET_ID}）把 <b>服務帳戶的 client_email</b> 加為 Viewer/Editor。</li>
            <li>再按 Redeploy。</li>
          </ol>
        </div>
        """
        return render_template_string(TEMPLATE.replace(
            "</div>\n</body>", help_html + "</div>\n</body>"),
                                      results=[],
                                      keyword="",
                                      columns=[],
                                      categories=[],
                                      companies=[],
                                      company_filter="")

    keyword = request.args.get('keyword', '').strip()
    company_filter = request.args.get('company_filter', '').strip()

    results, columns, companies = [], [], []
    if keyword:
        try:
            results, all_fields = get_results(keyword, categories)
        except Exception as e:
            return f"查詢發生錯誤：{e}", 500

        # 產生唯一 Company 清單（依首次出現順序）
        seen = set()
        for r in results:
            c = r.get('Company', '').strip()
            if c and c not in seen:
                seen.add(c)
                companies.append(c)

        # 依公司下拉篩選
        if company_filter:
            results = [
                r for r in results
                if r.get('Company', '').strip() == company_filter
            ]

        # 欄位順序：Type → Company → Title → Video url → 分類 → 來源工作表 → 其他
        def pick_columns(cols):
            order, added = [], set()

            def add(name):
                if name in cols and name not in added:
                    order.append(name)
                    added.add(name)

            add('Type')
            add('Company')
            add('Title')
            add('Video url')
            add('分類')
            add('來源工作表')
            for c in cols:
                if c not in added and not is_type_col(c):
                    order.append(c)
                    added.add(c)
            return order

        columns = pick_columns(all_fields)

    return render_template_string(TEMPLATE,
                                  results=results,
                                  keyword=keyword,
                                  columns=columns,
                                  categories=categories,
                                  companies=companies,
                                  company_filter=company_filter)


if __name__ == '__main__':
    # 本地（Replit）開發時才會執行；Vercel 由 @vercel/python 匯入 app 即可
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
