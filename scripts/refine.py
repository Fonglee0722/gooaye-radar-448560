"""B: 精煉進場條件  C: 族群/個股深挖. 基於股癌看多標的, 持有90天(B策略基礎).
進場特徵用 technical.read_signal; 報酬用 fullrun.fwd(抱90天)。
"""
import json, sys, statistics as st
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from technical import read_signal
from fullrun import prices, fwd, LAG

ROOT = Path(__file__).resolve().parent.parent
ETF = {'0050.TW','006208.TW','VOO','VTI','SPY','0056.TW','00878.TW','IVV','VT','QQQ'}
tw_ind = json.load(open(ROOT / "data" / "tw_industry.json"))
US_SECTOR = {
    'NVDA':'AI半導體','AMD':'AI半導體','AVGO':'AI半導體','MRVL':'AI半導體','ARM':'AI半導體',
    'INTC':'半導體','QCOM':'半導體','MU':'記憶體','ASML':'半導體設備','AMAT':'半導體設備',
    'ALAB':'AI連接','CRDO':'AI連接','LITE':'光通訊','COHR':'光通訊','AXTI':'光通訊','AAOI':'光通訊',
    'META':'網路平台','GOOGL':'網路平台','AMZN':'雲端電商','MSFT':'雲端軟體','AAPL':'消費電子',
    'TSLA':'電動車','NFLX':'網路平台','ORCL':'雲端軟體','PLTR':'軟體','SNOW':'軟體','CFLT':'軟體',
    'CRWD':'資安','DDOG':'軟體','NOW':'軟體','NET':'軟體','VRT':'AI基建','SMCI':'AI伺服器',
    'DELL':'AI伺服器','FLEX':'代工','PI':'物聯網','NBIS':'雲端','CRWV':'雲端','COIN':'加密',
    'HOOD':'金融科技','ASTS':'衛星','SBLK':'航運',
}

def sector_of(m):
    if m["market"] == "US":
        return US_SECTOR.get(m["ticker"], "其他美股")
    return tw_ind.get(m["ticker"].split(".")[0], "其他台股")

def load():
    seen = set(); out = []
    for m in json.load(open(ROOT / "data" / "llm_picks.json")):
        if m.get("stance") != "bull" or not m.get("ticker"): continue
        if m.get("market") not in ("US", "TW") or m["ticker"] in ETF: continue
        k = (m["ep"], m["ticker"])
        if k in seen: continue
        seen.add(k); out.append(m)
    return out

def enrich():
    rows = []
    for m in load():
        s = prices(m["ticker"])
        if s is None: continue
        _, r = fwd(s, m["date"], LAG[m["market"]])
        if r is None or r.get(90) is None: continue
        sig = read_signal(m["ticker"], m["date"])
        if not sig: continue
        rows.append({**m, "bh90": r[90], "sector": sector_of(m),
                     "trend": sig["trend"], "rsi": sig["rsi"],
                     "vsma20": sig["vs_ma20%"], "breakout": sig["breakout"],
                     "vol_surge": sig["vol_surge"], "macd": sig["macd_hist"]})
    return rows

def stat(vals):
    if len(vals) < 5: return None
    n = len(vals)
    return f"n={n:>4} 平均{st.mean(vals):>6.1f}% 中位{st.median(vals):>6.1f}% 勝率{sum(1 for v in vals if v>0)/n*100:>5.1f}%"

def partB(rows):
    print("\n" + "="*82)
    print("B 精煉進場條件 (股癌看多→抱90天, 各種濾網疊加)")
    print("="*82)
    def show(name, filt):
        allr = [r["bh90"] for r in rows if filt(r)]
        oos = [r["bh90"] for r in rows if filt(r) and int(r["date"][:4]) >= 2024]
        a = stat(allr); o = stat(oos)
        print(f"  {name:<26} 全期: {a or '樣本不足':<42} | 後段2024-26: {o or '樣本不足'}")
    up = lambda r: r["trend"] == "多頭排列"
    show("(基準)全部看多", lambda r: True)
    show("多頭排列", up)
    show("多頭排列+RSI<70未過熱", lambda r: up(r) and r["rsi"] < 70)
    show("多頭排列+離MA20≤8%不追高", lambda r: up(r) and r["vsma20"] <= 8)
    show("多頭排列+RSI<70+離MA20≤8%", lambda r: up(r) and r["rsi"] < 70 and r["vsma20"] <= 8)
    show("多頭排列+帶量突破", lambda r: up(r) and r["breakout"] and r["vol_surge"])
    show("多頭排列+MACD翻正", lambda r: up(r) and r["macd"] > 0)

def partC(rows):
    for mk, lab in (("US", "美股"), ("TW", "台股")):
        print("\n" + "="*82)
        print(f"C 族群深挖 — {lab}: 只看『多頭排列』進場, 抱90天, 按產業/類股 (依中位數排序, n≥8)")
        print("="*82)
        sub = [r for r in rows if r["market"] == mk and r["trend"] == "多頭排列"]
        by = {}
        for r in sub:
            by.setdefault(r["sector"], []).append(r["bh90"])
        ranked = sorted(((sec, v) for sec, v in by.items() if len(v) >= 8),
                        key=lambda x: -st.median(x[1]))
        for sec, v in ranked:
            n = len(v)
            print(f"  {sec:<12} n={n:>3}  平均{st.mean(v):>6.1f}%  中位{st.median(v):>6.1f}%  勝率{sum(1 for x in v if x>0)/n*100:>5.1f}%")

def leaderboard(rows):
    print("\n" + "="*82)
    print("個股榜 — 他最常看多的標的(n≥10), 只算『多頭排列』進場抱90天")
    print("="*82)
    by = {}
    for r in rows:
        if r["trend"] == "多頭排列":
            by.setdefault((r["name"], r["ticker"]), []).append(r["bh90"])
    ranked = sorted(((k, v) for k, v in by.items() if len(v) >= 10), key=lambda x: -st.median(x[1]))
    print("  最會發酵 Top12:")
    for (nm, tk), v in ranked[:12]:
        print(f"    {nm[:12]:<12}{tk:<10} n={len(v):>3} 中位{st.median(v):>6.1f}% 勝率{sum(1 for x in v if x>0)/len(v)*100:>5.0f}%")
    print("  最雷 Bottom8:")
    for (nm, tk), v in ranked[-8:]:
        print(f"    {nm[:12]:<12}{tk:<10} n={len(v):>3} 中位{st.median(v):>6.1f}% 勝率{sum(1 for x in v if x>0)/len(v)*100:>5.0f}%")

if __name__ == "__main__":
    rows = enrich()
    json.dump([{k:(round(v,2) if isinstance(v,float) else v) for k,v in r.items()} for r in rows],
              open(ROOT/"output"/"refine.json","w"), ensure_ascii=False)
    print(f"有效看多標的(有K線+特徵): {len(rows)} 筆")
    partB(rows)
    partC(rows)
    leaderboard(rows)
