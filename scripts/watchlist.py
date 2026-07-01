"""大總表(追蹤清單) — 最近3個月股癌看多標的, 每檔一列, 線型即時更新到最新交易日.
給出當前訊號 + 進場參考 + 風控參考 + 他為何看多。輸出 output/watchlist.html
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from technical import read_signal
from refine import sector_of
from dashboard import SECTOR_HIST

import datetime as _dt
ROOT = Path(__file__).resolve().parent.parent
TODAY = _dt.date.today().isoformat()                                  # 今天(動態)
SINCE = (_dt.date.today() - _dt.timedelta(days=100)).isoformat()      # 最近約三個月

def classify(sig, mk, sec_win):
    """依當前線型給訊號 + 進場參考 + 風控參考。"""
    t = sig["trend"]; rsi = sig["rsi"]; v = sig["vs_ma20%"]
    close = sig["close"]; ma20 = sig["ma20"]; ma60 = sig["ma60"]
    if t == "空頭排列":
        return "⛔ 轉弱·觀望", "—", "趨勢向下, 均線空頭排列, 不進場", f"跌破中"
    if t == "盤整/糾結":
        return "⏳ 等站上20日均線", f"站上 {ma20}", "均線糾結方向未明, 等收盤站上20日均線再進", f"20日均線 {ma20}"
    # 多頭排列
    if mk == "US" and sig["breakout"] and sig["vol_surge"]:
        return "🔥 帶量突破·可進", f"現價 {close}", "創20日新高且爆量, 美股此型最強", f"60日均線 {ma60}"
    if rsi >= 75 or v >= 12:
        return "⚠️ 過熱·等回均線", f"回到 {ma20} 附近", f"多頭但短線過熱(RSI {rsi}, 離20日線+{v}%), 追高風險大", f"60日均線 {ma60}"
    return "✅ 可進場", f"現價 {close}", f"多頭排列, 離20日線+{v}%未過熱, 站穩均線之上", f"60日均線 {ma60}"

def build():
    picks = [p for p in json.load(open(ROOT / "data" / "llm_picks.json"))
             if p["stance"] == "bull" and p.get("ticker") and p["market"] in ("US", "TW")
             and p["date"] >= SINCE and p["ticker"] not in
             {'0050.TW','006208.TW','VOO','VTI','SPY','0056.TW','00878.TW'}]
    byt = {}
    for p in picks:
        d = byt.setdefault(p["ticker"], {"name": p["name"], "market": p["market"],
                                          "mentions": [], "reason": p.get("reason", "")})
        d["mentions"].append((p["ep"], p["date"]))
        if p["date"] >= max(m[1] for m in d["mentions"]):
            d["reason"] = p.get("reason", d["reason"]); d["name"] = p["name"]
    rows = []
    for tk, d in byt.items():
        sig = read_signal(tk, TODAY)
        if not sig:
            continue
        sec = sector_of({"market": d["market"], "ticker": tk})
        win, med = SECTOR_HIST.get(sec, (None, None))
        signal, entry, entry_reason, risk = classify(sig, d["market"], win or 50)
        last_ep, last_date = sorted(d["mentions"])[-1]
        star = (signal.startswith(("✅", "🔥")) and (win or 0) >= 60)
        rows.append({"ticker": tk, "name": d["name"], "market": d["market"],
                     "sector": sec, "win": win, "med": med, "n": len(d["mentions"]),
                     "last_ep": last_ep, "last_date": last_date, "reason": d["reason"],
                     "trend": sig["trend"], "rsi": sig["rsi"], "vsma20": sig["vs_ma20%"],
                     "close": sig["close"], "asof": sig["asof"],
                     "signal": signal, "entry": entry, "entry_reason": entry_reason, "risk": risk,
                     "star": star})
    order = {"✅": 0, "🔥": 0, "⚠️": 1, "⏳": 2, "⛔": 3}
    rows.sort(key=lambda r: (order.get(r["signal"][0], 9), -(r["win"] or 0)))
    return rows

CSS = """*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'PingFang TC',sans-serif;background:#f5f5f4;color:#1c1c1a;line-height:1.55;padding:20px}
h1{font-size:21px;font-weight:600}.sub{color:#77756e;font-size:13px;margin:2px 0 14px}
.legend{font-size:12px;color:#5f5e5a;background:#fff;border:1px solid #e5e3dc;border-radius:8px;padding:10px 13px;margin-bottom:14px}
.legend b{color:#1c1c1a}
table{width:100%;border-collapse:collapse;font-size:12.5px;background:#fff;border:1px solid #e5e3dc;border-radius:10px;overflow:hidden}
th{text-align:left;color:#77756e;font-weight:500;padding:8px;background:#faf9f6;border-bottom:1px solid #e5e3dc;position:sticky;top:0}
td{padding:8px;border-bottom:1px solid #f0efe9;vertical-align:top}
tr.star td{background:#eefaf3}
.badge{display:inline-block;font-size:10.5px;padding:2px 6px;border-radius:6px;font-weight:500;white-space:nowrap}
.b-us{background:#e6f1fb;color:#0c447c}.b-tw{background:#faeeda;color:#633806}
.b-up{background:#e1f5ee;color:#0f6e56}.b-flat{background:#f1efe8;color:#5f5e5a}.b-down{background:#fceaea;color:#a32d2d}
.tk{font-family:ui-monospace,monospace;color:#77756e;font-size:11px}
.sig-buy{color:#0f6e56;font-weight:600}.sig-wait{color:#854f0b}.sig-no{color:#a32d2d}
.win-hi{color:#0f6e56;font-weight:500}.win-lo{color:#a32d2d}
.small{font-size:11px;color:#8a8880}"""

def esc(s): return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def render(rows):
    trs = []
    for r in rows:
        mk = f'<span class="badge {"b-us" if r["market"]=="US" else "b-tw"}">{"美"if r["market"]=="US" else "台"}</span>'
        tb = {"多頭排列":"b-up","盤整/糾結":"b-flat","空頭排列":"b-down"}.get(r["trend"],"b-flat")
        if r["win"] is not None:
            wc = "win-hi" if r["win"] >= 60 else "win-lo"
            hist = f'<span class="{wc}">勝率{r["win"]}% 中位{r["med"]:+d}%</span>'
        else:
            hist = '<span class="small">—</span>'
        sc = "sig-buy" if r["signal"][0] in "✅🔥" else ("sig-wait" if r["signal"][0] in "⚠️⏳" else "sig-no")
        star = "★ " if r["star"] else ""
        trs.append(
            f'<tr class="{"star" if r["star"] else ""}">'
            f'<td>{star}<b>{esc(r["name"])}</b> {mk}<br><span class="tk">{r["ticker"]}</span></td>'
            f'<td>{esc(r["sector"])}<br>{hist}</td>'
            f'<td><span class="badge {tb}">{r["trend"]}</span><br><span class="small">離20日線{r["vsma20"]:+.0f}% · RSI{r["rsi"]:.0f}</span></td>'
            f'<td class="{sc}">{r["signal"]}</td>'
            f'<td>{esc(r["entry"])}<br><span class="small">{esc(r["entry_reason"])}</span></td>'
            f'<td class="small">{esc(r["risk"])}</td>'
            f'<td class="small">EP{r["last_ep"]} · 提{r["n"]}次<br>{esc(r["reason"])}</td></tr>')
    asof = rows[0]["asof"] if rows else TODAY
    buy_n = sum(1 for r in rows if r["signal"][0] in "✅🔥")
    legend = ('<div class="legend"><b>訊號:</b> ✅可進場 / 🔥帶量突破 / ⚠️過熱等回檔 / ⏳等站上均線 / ⛔轉弱觀望。 '
              '<b>★</b>=可進場且屬強勢族群。<br>'
              '<b>多頭排列</b>=收盤>20日均線>60日均線(趨勢向上)。<b>進場參考</b>照回測: 多頭排列才進、不追過熱。<br>'
              '<b>風控參考</b>=跌破60日均線視為趨勢轉弱。<b>注意:</b> 回測顯示「機械式停損反而砍掉贏家」, 此欄僅供風險意識, 策略基準是抱約90天不亂停損。此為回測統計, 非投資建議。</div>')
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>股癌追蹤總表</title><style>{CSS}</style></head><body>'
            f'<h1>股癌追蹤總表</h1>'
            f'<div class="sub">最近三個月看多標的 · 線型即時更新至 {asof} · 共{len(rows)}檔, {buy_n}檔目前可進場</div>'
            f'{legend}<table><tr><th>標的</th><th>族群/歷史勝率</th><th>目前線型</th><th>訊號</th>'
            f'<th>進場參考</th><th>風控參考</th><th>他為何看多</th></tr>{"".join(trs)}</table></body></html>')

if __name__ == "__main__":
    rows = build()
    (ROOT / "output" / "watchlist.html").write_text(render(rows), encoding="utf-8")
    print(f"產生 output/watchlist.html — {len(rows)} 檔")
    print(f"目前可進場(✅🔥): {sum(1 for r in rows if r['signal'][0] in '✅🔥')} 檔")
    for r in rows[:8]:
        print(f"  {r['signal'][:6]:<8} {r['name'][:10]:<10} {r['sector'][:8]:<8} {r['trend']:<8} 離線{r['vsma20']:+.0f}%")
