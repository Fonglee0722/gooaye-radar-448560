"""技術分析模組 (信號B) — 完全獨立於股癌逐字稿, 只吃價量.

職責: 對任一標的, 在「參考日(=股癌提及日)」當下讀出技術狀態,
      給出進場訊號 / 建議停損 / 出場條件, 並可回測「擇時進場」是否優於無腦買。

指標: SMA20/60, RSI14, MACD(12,26,9), ATR14, 20日唐奇安通道(Donchian), 量能。
不依賴 backtest.py; 自帶 OHLCV 快取於 data/ohlcv/。
"""
import json, sys
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
OHLCV = ROOT / "data" / "ohlcv"; OHLCV.mkdir(parents=True, exist_ok=True)

def get_ohlcv(ticker, start="2025-01-01"):
    fp = OHLCV / f"{ticker.replace('.','_')}.csv"
    if fp.exists():
        df = pd.read_csv(fp, parse_dates=["Date"], index_col="Date")
        if len(df):
            return df
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True,
                     multi_level_index=False)
    if len(df):
        df.index.name = "Date"
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        df.to_csv(fp)
    return df

def indicators(df):
    c = df["Close"]
    out = pd.DataFrame(index=df.index)
    out["close"] = c
    out["ma20"] = c.rolling(20).mean()
    out["ma60"] = c.rolling(60).mean()
    # RSI14 (Wilder)
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    out["rsi"] = 100 - 100 / (1 + up / dn)
    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_sig"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_sig"]
    # ATR14
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - c.shift()).abs(),
                    (df["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    out["atr"] = tr.ewm(alpha=1/14, adjust=False).mean()
    # Donchian 20 (前一日為止的高低, 不含當日避免lookahead)
    out["hh20"] = df["High"].rolling(20).max().shift(1)
    out["ll20"] = df["Low"].rolling(20).min().shift(1)
    out["vol"] = df["Volume"]
    out["vol_ma20"] = df["Volume"].rolling(20).mean()
    return out

def read_signal(ticker, ref_date):
    """讀參考日(含)之前最後一根K的技術狀態, 給進場判斷。"""
    df = get_ohlcv(ticker)
    if df is None or len(df) == 0:
        return None
    ind = indicators(df)
    sub = ind[ind.index <= pd.Timestamp(ref_date)].dropna(subset=["ma60", "atr"])
    if len(sub) == 0:
        return None
    r = sub.iloc[-1]
    close, ma20, ma60 = r["close"], r["ma20"], r["ma60"]
    rsi, atr = r["rsi"], r["atr"]
    # 趨勢
    if close > ma20 > ma60:
        trend = "多頭排列"
    elif close < ma20 < ma60:
        trend = "空頭排列"
    else:
        trend = "盤整/糾結"
    # 進場訊號分類
    above_ma20_pct = (close / ma20 - 1) * 100
    breakout = close >= r["hh20"]
    vol_surge = r["vol"] > 1.5 * r["vol_ma20"] if pd.notna(r["vol_ma20"]) else False
    if trend == "空頭排列":
        signal, advice = "趨勢偏空", "觀望, 不宜進場"
    elif breakout and vol_surge:
        signal, advice = "帶量突破", "可順勢進場(突破買)"
    elif rsi >= 75 or above_ma20_pct >= 12:
        signal, advice = "短線過熱", "追高風險大, 等回檔均線再進"
    elif trend == "多頭排列" and above_ma20_pct <= 4:
        signal, advice = "回測均線", "靠近上升均線, 偏好進場點"
    elif trend == "多頭排列":
        signal, advice = "多頭續勢", "可分批進場"
    else:
        signal, advice = "盤整待變", "等突破或跌破再動作"
    stop = round(close - 2 * atr, 2)  # 停損: 進場價下方2倍ATR
    return {
        "trend": trend, "signal": signal, "advice": advice,
        "close": round(close, 2), "rsi": round(rsi, 1),
        "ma20": round(ma20, 2), "ma60": round(ma60, 2),
        "macd_hist": round(r["macd_hist"], 3),
        "vs_ma20%": round(above_ma20_pct, 1),
        "atr": round(atr, 2), "stop": stop,
        "stop_pct": round((stop / close - 1) * 100, 1),
        "breakout": bool(breakout), "vol_surge": bool(vol_surge),
        "asof": str(r.name.date()),  # 這根K線的日期(資料截至)
    }

def ta_timed_trade(ticker, ref_date, max_wait=10, max_hold=60, exit_ma="ma20"):
    """擇時回測: 從參考日起, 等技術買訊(突破20日高 或 站上MA20)才進場;
    出場條件: 收盤跌破MA20(移動停利) 或 觸及2ATR停損 或 達max_hold上限。
    回傳該筆交易報酬% 與進出場日; 無訊號則不交易。"""
    df = get_ohlcv(ticker)
    if df is None or len(df) == 0:
        return None
    ind = indicators(df).dropna(subset=["ma20", "atr"])
    fut = ind[ind.index >= pd.Timestamp(ref_date)]
    if len(fut) == 0:
        return None
    # 找進場: max_wait 交易日內首次(突破20日高 或 收盤站上MA20)
    entry = None
    for i, (dtix, row) in enumerate(fut.iterrows()):
        if i > max_wait:
            break
        if row["close"] >= row["hh20"] or row["close"] > row["ma20"]:
            entry = (dtix, float(row["close"]), float(row["atr"])); break
    if entry is None:
        return {"traded": False, "reason": "等不到買訊"}
    edate, eprice, eatr = entry
    stop = eprice - 2 * eatr
    hold = ind[ind.index > edate]
    for j, (dtix, row) in enumerate(hold.iterrows()):
        hit_stop = row["close"] < stop
        below_ma = row["close"] < row[exit_ma]
        if hit_stop or below_ma or j >= max_hold:
            xprice = float(row["close"])
            reason = "停損" if hit_stop else ("跌破MA20出場" if below_ma else "持有上限")
            return {"traded": True, "entry_date": str(edate.date()), "entry": round(eprice, 2),
                    "exit_date": str(dtix.date()), "exit": round(xprice, 2),
                    "ret": round((xprice / eprice - 1) * 100, 2), "days": (dtix - edate).days,
                    "exit_reason": reason}
    # 還沒出場(資料到頂)
    last = hold.iloc[-1]
    return {"traded": True, "entry_date": str(edate.date()), "entry": round(eprice, 2),
            "exit_date": str(hold.index[-1].date()), "exit": round(float(last["close"]), 2),
            "ret": round((float(last["close"]) / eprice - 1) * 100, 2),
            "days": (hold.index[-1] - edate).days, "exit_reason": "尚未出場"}

if __name__ == "__main__":
    picks = json.load(open(ROOT / "data" / "picks.json"))
    print("="*100)
    print("技術分析訊號 (信號B, 獨立於股癌) — 在股癌提及當日的線圖狀態與進出場建議")
    print("="*100)
    print(f"{'標的':<10}{'族群':<14}{'趨勢':<10}{'RSI':>5} {'離MA20':>7} {'進場訊號':<10}{'建議':<22}{'停損':>8}")
    print("-"*100)
    seen = set()
    for p in picks:
        k = (p["name"], p["date"])
        if k in seen:
            continue
        seen.add(k)
        s = read_signal(p["ticker"], p["date"])
        if not s:
            print(f"{p['name'][:10]:<10}(無資料)"); continue
        print(f"{p['name'][:10]:<10}{(p.get('group') or '')[:14]:<14}{s['trend']:<10}"
              f"{s['rsi']:>5} {s['vs_ma20%']:>6}% {s['signal']:<10}{s['advice']:<22}"
              f"{s['stop']:>8}({s['stop_pct']}%)")
