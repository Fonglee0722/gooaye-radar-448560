"""合併成單一連結 — 一個 index.html, 上方兩個頁籤切換:
   ①追蹤總表(即時訊號)  ②每集卡片(摘要重點)。純JS切換, 無外部相依。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import watchlist as W
import dashboard as D

ROOT = Path(__file__).resolve().parent.parent

def inner(html):
    return html.split("<body>", 1)[1].split("</body>", 1)[0]

def main():
    wl_rows = W.build()
    wl_body = inner(W.render(wl_rows))
    dash_cards = D.build()
    dash_body = inner(D.render(dash_cards))
    asof = wl_rows[0]["asof"] if wl_rows else W.TODAY
    buy_n = sum(1 for r in wl_rows if r["signal"][0] in "✅🔥")

    tabcss = """
.topbar{display:flex;gap:8px;margin-bottom:16px;position:sticky;top:0;background:#f5f5f4;padding:8px 0;z-index:10}
.tab{padding:8px 16px;border:1px solid #e5e3dc;border-radius:8px;background:#fff;cursor:pointer;font-size:14px;font-weight:500;color:#5f5e5a}
.tab.active{background:#1c1c1a;color:#fff;border-color:#1c1c1a}
.view{display:none}.view.active{display:block}
"""
    js = """
function show(v){
  document.querySelectorAll('.view').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));
  document.getElementById('v-'+v).classList.add('active');
  document.getElementById('t-'+v).classList.add('active');
}
"""
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>股癌選股工具</title><style>{W.CSS}\n{D.CSS}\n{tabcss}</style></head><body>
<div class="topbar">
  <div class="tab active" id="t-wl" onclick="show('wl')">📋 追蹤總表 ({buy_n}檔可進場)</div>
  <div class="tab" id="t-dash" onclick="show('dash')">📅 每集重點</div>
</div>
<div class="view active" id="v-wl">{wl_body}</div>
<div class="view" id="v-dash">{dash_body}</div>
<script>{js}</script></body></html>"""
    out = ROOT / "output" / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"產生單一連結 {out}")
    print(f"追蹤總表 {len(wl_rows)} 檔 ({buy_n} 可進場) · 每集卡片 {len(dash_cards)} 集 · 資料截至 {asof}")

if __name__ == "__main__":
    main()
