"""技術分析策略回測 — 在「股癌看多」標的上, 比較三種策略.
A 無腦跟單(買進抱90天)  B 只買多頭排列  C 多頭排列進+跌破MA60/2ATR停損出
分行情(多/空頭) + 分時期(2020-2023 / 2024-2026 walk-forward)。
"""
import json, sys, statistics as st
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from technical import get_ohlcv, indicators, ta_timed_trade
from fullrun import prices, fwd, regime, BENCH, LAG

ROOT = Path(__file__).resolve().parent.parent
ETF = {'0050.TW','006208.TW','VOO','VTI','SPY','0056.TW','00878.TW','IVV','VT','QQQ'}
HOLD = 90

def trend_at(ticker, ref_date):
    df = get_ohlcv(ticker)
    if df is None or len(df) == 0:
        return None
    ind = indicators(df)
    sub = ind[ind.index <= pd.Timestamp(ref_date)].dropna(subset=["ma60"])
    if len(sub) == 0:
        return None
    r = sub.iloc[-1]
    if r["close"] > r["ma20"] > r["ma60"]:
        return "多頭排列"
    if r["close"] < r["ma20"] < r["ma60"]:
        return "空頭排列"
    return "盤整"

def load_picks():
    seen = set(); out = []
    for m in json.load(open(ROOT / "data" / "llm_picks.json")):
        if m.get("stance") != "bull" or not m.get("ticker"): continue
        if m.get("market") not in ("US", "TW") or m["ticker"] in ETF: continue
        k = (m["ep"], m["ticker"])
        if k in seen: continue
        seen.add(k); out.append(m)
    return out

def stats(vals):
    if not vals: return None
    n = len(vals)
    return dict(n=n, mean=st.mean(vals), med=st.median(vals),
               win=sum(1 for v in vals if v > 0)/n*100, worst=min(vals))

def pr(label, s):
    if not s: print(f"  {label:<22} (無樣本)"); return
    print(f"  {label:<22} n={s['n']:>4}  平均{s['mean']:>6.1f}%  中位{s['med']:>6.1f}%  勝率{s['win']:>5.1f}%  最差{s['worst']:>7.1f}%")

def run():
    picks = load_picks()
    rec = []
    for m in picks:
        mk = m["market"]; tk = m["ticker"]
        s = prices(tk)
        if s is None: continue
        edate, r = fwd(s, m["date"], LAG[mk])
        if r is None or r.get(HOLD) is None: continue
        bh = r[HOLD]                      # A: 買進抱90天
        tr = trend_at(tk, m["date"])      # 進場當下趨勢
        ta = ta_timed_trade(tk, m["date"], max_wait=10, max_hold=HOLD, exit_ma="ma60")
        rec.append({"ep": m["ep"], "date": m["date"], "market": mk, "ticker": tk,
                    "regime": regime(mk, m["date"]), "year": int(m["date"][:4]),
                    "bh": bh, "trend": tr,
                    "ta": (ta["ret"] if ta and ta.get("traded") else None),
                    "ta_traded": bool(ta and ta.get("traded"))})
    json.dump([{k:(round(v,2) if isinstance(v,float) else v) for k,v in x.items()} for x in rec],
              open(ROOT/"output"/"ta_backtest.json","w"), ensure_ascii=False)

    def block(rows, title):
        print(f"\n{'='*78}\n{title}  (n={len(rows)})")
        A = [x["bh"] for x in rows]
        B = [x["bh"] for x in rows if x["trend"] == "多頭排列"]
        C = [x["ta"] for x in rows if x["ta"] is not None]
        pr("A 無腦跟單(抱90)", stats(A))
        pr("B 只買多頭排列(抱90)", stats(B))
        pr("C 多頭排列+紀律出場", stats(C))

    for mk in ("US", "TW"):
        sub = [x for x in rec if x["market"] == mk]
        nm = "美股" if mk == "US" else "台股"
        block(sub, f"### {nm} 全部")
        block([x for x in sub if x["regime"] == "多頭"], f"### {nm}【多頭行情】")
        block([x for x in sub if x["regime"] == "空頭"], f"### {nm}【空頭行情】")
        block([x for x in sub if x["year"] <= 2023], f"### {nm} 前段 2020-2023 (找規律)")
        block([x for x in sub if x["year"] >= 2024], f"### {nm} 後段 2024-2026 (驗證)")

if __name__ == "__main__":
    run()
