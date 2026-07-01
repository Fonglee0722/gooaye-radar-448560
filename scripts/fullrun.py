"""全樣本回測 — 所有671集提及 × 各horizon × 分行情(多頭/空頭) × 分市場.

行情判定: 提及當日, 該市場基準(台股0050 / 美股QQQ)收盤 是否站上 200日均線。
進場延遲: 台股+1交易日, 美股當日。alpha = 標的報酬 - 同期基準報酬。
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PR = ROOT / "data" / "prices"
HORIZONS = [7, 14, 30, 60, 90]
BENCH = {"US": "QQQ", "TW": "0050.TW"}
LAG = {"US": 0, "TW": 1}

_cache = {}
def prices(t):
    if t not in _cache:
        fp = PR / f"{t.replace('.','_')}.csv"
        if fp.exists():
            s = pd.read_csv(fp, parse_dates=["Date"], index_col="Date")["Close"].dropna()
            _cache[t] = s
        else:
            _cache[t] = None
    return _cache[t]

def fwd(series, ep_date, lag):
    after = series[series.index >= pd.Timestamp(ep_date)]
    if len(after) <= lag:
        return None, None
    edate = after.index[lag]; entry = float(after.iloc[lag])
    rets = {}
    for h in HORIZONS:
        win = series[series.index >= edate + pd.Timedelta(days=h)]
        rets[h] = (float(win.iloc[0]) / entry - 1) * 100 if len(win) else None
    return edate, rets

def regime(market, ep_date):
    s = prices(BENCH[market])
    if s is None:
        return "?"
    hist = s[s.index <= pd.Timestamp(ep_date)]
    if len(hist) < 200:
        return "?"
    return "多頭" if hist.iloc[-1] > hist.tail(200).mean() else "空頭"

def build():
    ms = json.load(open(ROOT / "data" / "all_mentions.json"))
    rows = []
    for m in ms:
        s = prices(m["ticker"])
        b = prices(BENCH[m["market"]])
        if s is None or b is None:
            continue
        lag = LAG[m["market"]]
        edate, r = fwd(s, m["date"], lag)
        if r is None:
            continue
        _, br = fwd(b, m["date"], lag)
        reg = regime(m["market"], m["date"])
        row = {**m, "regime": reg}
        for h in HORIZONS:
            row[f"r{h}"] = r[h]
            row[f"a{h}"] = (r[h] - br[h]) if (br and r[h] is not None and br[h] is not None) else None
        rows.append(row)
    return rows

def tab(rows, label):
    print(f"\n▌{label}  (n={len(rows)}筆提及)")
    print(f"{'horizon':>8} | {'樣本':>5} | {'絕對均':>7} | {'α均':>7} | {'α中位':>7} | {'α勝率':>6}")
    print("-" * 56)
    for h in HORIZONS:
        rr = [x[f"r{h}"] for x in rows if x.get(f"r{h}") is not None]
        aa = [x[f"a{h}"] for x in rows if x.get(f"a{h}") is not None]
        if not aa:
            print(f"{('+'+str(h)+'d'):>8} | (無滿期)"); continue
        ravg = sum(rr)/len(rr); aavg = sum(aa)/len(aa)
        amed = sorted(aa)[len(aa)//2]; awin = sum(1 for v in aa if v > 0)/len(aa)*100
        print(f"{('+'+str(h)+'d'):>8} | {len(aa):>5} | {ravg:>6.2f}% | {aavg:>6.2f}% | {amed:>6.2f}% | {awin:>5.1f}%")

if __name__ == "__main__":
    rows = build()
    json.dump([{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}
               for r in rows], open(ROOT / "output" / "fullrun.json", "w"), ensure_ascii=False)
    print(f"=== 全樣本: {len(rows)} 筆有效提及 (有股價且至少滿7天) ===")
    for mk in ("US", "TW"):
        sub = [r for r in rows if r["market"] == mk]
        name = "美股(對QQQ)" if mk == "US" else "台股(對0050)"
        print("\n" + "=" * 60)
        print(f"### {name} — 全部")
        tab(sub, f"{name} 全行情")
        for reg in ("多頭", "空頭"):
            rs = [r for r in sub if r["regime"] == reg]
            if rs:
                tab(rs, f"{name} 只看【{reg}】行情")
