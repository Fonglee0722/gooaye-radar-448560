"""股癌逐字稿選股回測引擎 (v2: 美股+台股, 分層輸出).

輸入: data/picks.json -- 每筆 {ep, date, name, ticker, market, group, type, stance}
  market: 'US' / 'TW'        group: 族群/題材標籤      type: '個股'/'ETF'
  stance: 'bull'/'bear'/'mention'
進場: 節目日後第一個交易日收盤。horizon: +7/14/30/60/90 日曆天後最近交易日。
對照基準(算alpha): 美股 vs QQQ, 台股 vs 0050.TW。
輸出: ① 單檔明細 ② 按族群彙整 ③ 按市場彙整, 存 output/results.json + output/by_pick.csv
"""
import json, sys
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA, PRICES, OUT = ROOT / "data", ROOT / "data" / "prices", ROOT / "output"
PRICES.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
HORIZONS = [7, 14, 30, 60, 90]
BENCH = {"US": "QQQ", "TW": "0050.TW"}

ticker_map = json.load(open(DATA / "ticker_map.json"))

def market_of(ticker):
    return "TW" if ticker.endswith((".TW", ".TWO")) else "US"

def get_prices(ticker, start="2025-01-01"):
    fp = PRICES / f"{ticker.replace('.','_')}.csv"
    if fp.exists():
        df = pd.read_csv(fp, parse_dates=["Date"], index_col="Date")
        if len(df):
            return df
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True,
                     multi_level_index=False)
    if len(df):
        df.index.name = "Date"; df[["Close"]].to_csv(fp)
    return df[["Close"]] if len(df) else df

ENTRY_LAG = {"US": 0, "TW": 1}  # 進場延遲(交易日): 台股節目晚上發, 隔日才買得到

def _horizon_return(df, ep_date, lag=0):
    after = df[df.index >= pd.Timestamp(ep_date)]
    if len(after) <= lag:
        return None
    entry_date = after.index[lag]; entry = float(after["Close"].iloc[lag])
    rets = {}
    for h in HORIZONS:
        win = df[df.index >= entry_date + pd.Timedelta(days=h)]
        rets[h] = round((float(win["Close"].iloc[0]) / entry - 1) * 100, 2) if len(win) else None
    return entry_date, entry, rets

def fwd_returns(ticker, ep_date, market):
    df = get_prices(ticker)
    if df is None or len(df) == 0:
        return None
    lag = ENTRY_LAG.get(market, 0)
    r = _horizon_return(df, ep_date, lag)
    if r is None:
        return None
    entry_date, entry, rets = r
    bench = get_prices(BENCH[market])
    bret = _horizon_return(bench, ep_date, lag)[2] if bench is not None and len(bench) else {}
    res = {"entry_date": str(entry_date.date()), "entry": round(entry, 2)}
    for h in HORIZONS:
        res[f"r{h}"] = rets[h]
        b = bret.get(h)
        res[f"a{h}"] = round(rets[h] - b, 2) if (rets[h] is not None and b is not None) else None
    return res

def run(picks_path):
    rows = []
    for p in json.load(open(picks_path)):
        if p.get("stance", "bull") == "bear":
            continue
        tk = p.get("ticker") or ticker_map.get(p["name"])
        mk = p.get("market") or (market_of(tk) if tk else None)
        if not tk:
            rows.append({**p, "ticker": None, "note": "無代號"}); continue
        fr = fwd_returns(tk, p["date"], mk)
        if fr is None:
            rows.append({**p, "ticker": tk, "market": mk, "note": "無股價"}); continue
        rows.append({**p, "ticker": tk, "market": mk, **fr})
    return rows

def _stats(vals):
    n = len(vals)
    if not n:
        return None
    return n, sum(vals)/n, sorted(vals)[n//2], sum(1 for v in vals if v > 0)/n*100

def agg_table(rows, title, metric="a"):
    """metric='a' 用 alpha, 'r' 用絕對報酬"""
    lab = "超額α" if metric == "a" else "絕對"
    print(f"\n{title} (數字為{lab}報酬)")
    print(f"{'horizon':>8} | {'樣本':>4} | {'平均':>7} | {'中位':>7} | {'勝率':>6}")
    print("-" * 46)
    for h in HORIZONS:
        s = _stats([r[f"{metric}{h}"] for r in rows if r.get(f"{metric}{h}") is not None])
        if not s:
            print(f"{('+'+str(h)+'d'):>8} | (無)"); continue
        n, avg, med, win = s
        print(f"{('+'+str(h)+'d'):>8} | {n:>4} | {avg:>6.2f}% | {med:>6.2f}% | {win:>5.1f}%")

def by_pick(rows):
    print("\n" + "="*92)
    print("① 單檔明細 (每一個提及分開看, α=扣掉同期大盤的超額報酬)")
    print("="*92)
    print(f"{'EP':>4} {'日期':<10} {'標的':<10} {'市':<2} {'族群':<14} "
          f"{'a7':>6} {'a14':>6} {'a30':>6} {'a60':>6} {'a90':>6}")
    print("-"*92)
    for r in sorted(rows, key=lambda x: (x["date"], x["name"])):
        if "entry" not in r:
            continue
        f = lambda k: (f"{r[k]:+.1f}" if r.get(k) is not None else "—")
        print(f"{r['ep']:>4} {r['date']:<10} {r['name'][:10]:<10} {r['market']:<2} "
              f"{(r.get('group') or '')[:14]:<14} "
              f"{f('a7'):>6} {f('a14'):>6} {f('a30'):>6} {f('a60'):>6} {f('a90'):>6}")

def summarize(rows):
    valid = [r for r in rows if "entry" in r]
    by_pick(rows)
    print("\n" + "="*92)
    print("② 按市場彙整")
    for mk in ("US", "TW"):
        sub = [r for r in valid if r["market"] == mk]
        if sub:
            agg_table(sub, f"  ▌{mk} 美股" if mk=="US" else f"  ▌{mk} 台股", "a")
    print("\n" + "="*92)
    print("③ 按族群彙整")
    groups = {}
    for r in valid:
        groups.setdefault(r.get("group") or "其他", []).append(r)
    for g, sub in sorted(groups.items(), key=lambda x: -len(x[1])):
        agg_table(sub, f"  ▌{g} (n={len(sub)}檔)", "a")

if __name__ == "__main__":
    picks_path = sys.argv[1] if len(sys.argv) > 1 else DATA / "picks.json"
    rows = run(picks_path)
    json.dump(rows, open(OUT / "results.json", "w"), ensure_ascii=False, indent=2)
    valid = [r for r in rows if "entry" in r]
    if valid:
        pd.DataFrame(valid).to_csv(OUT / "by_pick.csv", index=False)
    summarize(rows)
    bad = [r for r in rows if r.get("note")]
    if bad:
        print("\n未納入:", ", ".join(f"EP{r['ep']}{r['name']}({r['note']})" for r in bad))
