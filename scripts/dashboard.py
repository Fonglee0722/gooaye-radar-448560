"""產生本機 HTML 儀表板 — 最近N個月每集: 摘要重點 + 可執行清單(高勝率組合標記).
輸出 output/dashboard.html (自包含, 直接用瀏覽器開)。
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from technical import read_signal
from refine import sector_of, US_SECTOR, tw_ind

import datetime as _dt
ROOT = Path(__file__).resolve().parent.parent
MONTHS_DATE = (_dt.date.today() - _dt.timedelta(days=100)).isoformat()   # 最近約三個月(動態)

# 各族群歷史統計(來自C分析: 多頭排列進場抱90天) -> (勝率, 中位數報酬)
SECTOR_HIST = {
    "光通訊": (100, 82), "記憶體": (80, 27), "AI半導體": (70, 12), "軟體": (73, 9),
    "雲端軟體": (84, 7), "網路平台": (64, 9), "雲端電商": (64, 6), "消費電子": (53, 2),
    "電動車": (54, 4), "半導體": (46, -5), "AI連接": (42, -11), "AI伺服器": (39, -8),
    "電子零組件業": (78, 10), "半導體業": (64, 9), "通信網路業": (64, 10),
    "其他電子業": (75, 6), "電腦及週邊設備業": (58, 3), "光電業": (20, -7),
}

def hi_prob(mk, sig, sector):
    """是否符合高勝率組合: 多頭排列 +(美股要帶量突破)+ 族群歷史勝率>=60%"""
    if not sig or sig["trend"] != "多頭排列":
        return False
    win = SECTOR_HIST.get(sector, (50, 0))[0]
    if win < 60:
        return False
    if mk == "US":
        return sig["breakout"] and sig["vol_surge"]
    return True  # 台股: 多頭排列即可

def build():
    eps = {e["n"]: e for e in json.load(open(ROOT / "data" / "transcripts.json"))}
    picks = {}
    for p in json.load(open(ROOT / "data" / "llm_picks.json")):
        picks.setdefault(p["ep"], []).append(p)
    recent = sorted([n for n, e in eps.items() if e["d"] >= MONTHS_DATE], reverse=True)
    cards = []
    for n in recent:
        e = eps[n]
        bulls = [p for p in picks.get(n, []) if p["stance"] == "bull" and p.get("ticker")
                 and p["market"] in ("US", "TW")]
        items = []
        for p in bulls:
            sig = read_signal(p["ticker"], p["date"])
            sector = sector_of(p)
            win, med = SECTOR_HIST.get(sector, (None, None))
            items.append({
                "name": p["name"], "ticker": p["ticker"], "market": p["market"],
                "sector": sector, "conviction": p.get("conviction", ""),
                "reason": p.get("reason", ""),
                "trend": sig["trend"] if sig else "無資料",
                "breakout": sig["breakout"] if sig else False,
                "rsi": sig["rsi"] if sig else None,
                "hist_win": win, "hist_med": med,
                "hi": hi_prob(p["market"], sig, sector),
            })
        items.sort(key=lambda x: (not x["hi"], x["market"] != "US"))
        cards.append({"ep": n, "date": e["d"], "title": e["t"],
                      "desc": e.get("desc", ""), "items": items})
    return cards

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'PingFang TC',sans-serif;background:#f5f5f4;color:#1c1c1a;
  line-height:1.6;padding:24px;max-width:960px;margin:0 auto}
h1{font-size:22px;font-weight:600;margin-bottom:4px}
.sub{color:#77756e;font-size:14px;margin-bottom:24px}
.card{background:#fff;border:1px solid #e5e3dc;border-radius:12px;padding:18px 20px;margin-bottom:16px}
.ep-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.ep-num{font-weight:600;font-size:16px}
.ep-date{color:#77756e;font-size:13px}
.ep-title{font-size:15px;color:#3c3a34}
.desc{font-size:13px;color:#77756e;background:#faf9f6;border-radius:8px;padding:8px 12px;margin:8px 0 14px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:#77756e;font-weight:500;padding:6px 8px;border-bottom:1px solid #e5e3dc}
td{padding:7px 8px;border-bottom:1px solid #f0efe9;vertical-align:top}
tr.hi td{background:#eefaf3}
.badge{display:inline-block;font-size:11px;padding:2px 7px;border-radius:6px;font-weight:500}
.b-hi{background:#1d9e75;color:#fff}
.b-us{background:#e6f1fb;color:#0c447c}
.b-tw{background:#faeeda;color:#633806}
.b-up{background:#e1f5ee;color:#0f6e56}
.b-flat{background:#f1efe8;color:#5f5e5a}
.b-down{background:#fceaea;color:#a32d2d}
.tk{font-family:ui-monospace,monospace;color:#77756e;font-size:12px}
.reason{color:#8a8880;font-size:12px}
.hist{font-size:12px}
.win-hi{color:#0f6e56;font-weight:500}.win-lo{color:#a32d2d}
.empty{color:#a8a69e;font-size:13px;font-style:italic}
.legend{font-size:12px;color:#77756e;margin-bottom:20px;background:#fff;border:1px solid #e5e3dc;
  border-radius:8px;padding:10px 14px}
"""

def esc(s): return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def render(cards):
    rows = []
    for c in cards:
        hi_n = sum(1 for it in c["items"] if it["hi"])
        head = (f'<div class="ep-head"><span class="ep-num">EP{c["ep"]}</span>'
                f'<span class="ep-date">{c["date"]}</span>'
                f'<span class="ep-title">{esc(c["title"])}</span>'
                + (f'<span class="badge b-hi">★ {hi_n} 檔符合高勝率組合</span>' if hi_n else '')
                + '</div>')
        desc = f'<div class="desc">{esc(c["desc"])}</div>' if c["desc"] else ''
        if c["items"]:
            trs = []
            for it in c["items"]:
                mk = '<span class="badge b-us">美股</span>' if it["market"] == "US" else '<span class="badge b-tw">台股</span>'
                tb = {"多頭排列": "b-up", "盤整": "b-flat", "空頭排列": "b-down"}.get(it["trend"], "b-flat")
                trend = f'<span class="badge {tb}">{it["trend"]}</span>'
                if it["market"] == "US" and it["breakout"]:
                    trend += ' <span class="badge b-up">帶量突破</span>'
                star = '★ ' if it["hi"] else ''
                if it["hist_win"] is not None:
                    cls = "win-hi" if it["hist_win"] >= 60 else "win-lo"
                    hist = f'<span class="hist {cls}">勝率{it["hist_win"]}% 中位{it["hist_med"]:+d}%</span>'
                else:
                    hist = '<span class="hist">—</span>'
                trs.append(
                    f'<tr class="{"hi" if it["hi"] else ""}"><td>{star}<b>{esc(it["name"])}</b> '
                    f'<span class="tk">{it["ticker"]}</span> {mk}</td>'
                    f'<td>{esc(it["sector"])}<br><span class="hist">{hist}</span></td>'
                    f'<td>{trend}</td>'
                    f'<td class="reason">{esc(it["reason"])}</td></tr>')
            body = ('<table><tr><th>標的</th><th>族群/歷史</th><th>目前線型</th><th>他為何看多</th></tr>'
                    + "".join(trs) + '</table>')
        else:
            body = '<div class="empty">本集無明確看多個股(可能純聊產業/生活)</div>'
        rows.append(f'<div class="card">{head}{desc}{body}</div>')
    legend = ('<div class="legend"><b>怎麼看:</b> ★綠底 = 符合回測出的高勝率組合'
              '(他看多 + 目前多頭排列 + 強勢族群，美股再加帶量突破)。'
              '「族群/歷史」= 該類股歷史上他看多後抱90天的勝率與中位數報酬。'
              '不設停損、抱約90天。此為回測統計非投資建議。</div>')
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>股癌選股儀表板</title><style>{CSS}</style></head><body>'
            f'<h1>股癌選股儀表板</h1>'
            f'<div class="sub">最近三個月 · 每集看多標的 × 技術線型 × 族群歷史勝率</div>'
            f'{legend}{"".join(rows)}</body></html>')

if __name__ == "__main__":
    cards = build()
    html = render(cards)
    out = ROOT / "output" / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"產生 {out}")
    print(f"涵蓋 {len(cards)} 集, 其中有看多個股的 {sum(1 for c in cards if c['items'])} 集")
    print(f"符合高勝率組合的標的總數: {sum(1 for c in cards for it in c['items'] if it['hi'])}")
