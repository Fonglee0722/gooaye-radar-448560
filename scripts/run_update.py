"""自動更新入口 (排程與本機共用).
1) 抓最新逐字稿包 → 找出尚未抽取的新集數 → LLM抽取(需 ANTHROPIC_API_KEY)
2) 更新最近三個月看多標的的股價/線型
3) 重生 docs/index.html (GitHub Pages 由此資料夾發佈)
本機測試: python scripts/run_update.py   CI: 同一支被 GitHub Actions 呼叫
"""
import json, os, sys, shutil, urllib.request, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))

PACK_URL = "https://whatmkreallysaid.com/transcripts.json.br"

def log(*a): print("[update]", *a, flush=True)

def fetch_transcripts():
    """下載並解壓最新逐字稿包, 回傳 episodes list。失敗則用本地既有檔。"""
    try:
        import brotli
        req = urllib.request.Request(PACK_URL, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=60).read()
        data = json.loads(brotli.decompress(raw))
        (DATA / "transcripts.json").write_text(json.dumps(data, ensure_ascii=False))
        log(f"逐字稿更新: {len(data)} 集 (最新 EP{max(e['n'] for e in data)})")
        return data
    except Exception as e:
        log(f"下載逐字稿失敗({e}), 改用本地既有檔")
        return json.load(open(DATA / "transcripts.json"))

def new_episodes(eps):
    done = set()
    fp = DATA / "llm_picks.json"
    if fp.exists():
        done = {r["ep"] for r in json.load(open(fp))}
    return sorted(e["n"] for e in eps if e["n"] not in done)

def update_prices():
    """更新最近三個月看多標的的 close 與 OHLCV 到最新交易日。"""
    import yfinance as yf
    since = (dt.date.today() - dt.timedelta(days=100)).isoformat()
    ETF = {'0050.TW','006208.TW','VOO','VTI','SPY','0056.TW','00878.TW'}
    picks = json.load(open(DATA / "llm_picks.json"))
    tks = sorted(set(r["ticker"] for r in picks if r["stance"] == "bull" and r.get("ticker")
                     and r["market"] in ("US", "TW") and r["ticker"] not in ETF
                     and r["date"] >= since)) + ["0050.TW", "QQQ"]
    (DATA / "prices").mkdir(exist_ok=True); (DATA / "ohlcv").mkdir(exist_ok=True)
    ok = 0
    for i in range(0, len(tks), 40):
        batch = tks[i:i+40]
        try:
            d = yf.download(batch, start="2020-01-01", progress=False, auto_adjust=True,
                            group_by="ticker", threads=True)
        except Exception:
            d = None
        for t in batch:
            df = None
            try:
                df = d[t] if (d is not None and t in d.columns.get_level_values(0)) else None
            except Exception:
                df = None
            if df is None:
                try:
                    df = yf.download(t, start="2020-01-01", progress=False, auto_adjust=True,
                                     multi_level_index=False)
                except Exception:
                    df = None
            if df is None or not len(df) or "Close" not in df:
                continue
            key = t.replace(".", "_")
            df[["Close"]].dropna().rename_axis("Date").to_csv(DATA / "prices" / f"{key}.csv")
            cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df]
            df[cols].dropna(subset=["Close"]).rename_axis("Date").to_csv(DATA / "ohlcv" / f"{key}.csv")
            ok += 1
    log(f"股價更新: {ok}/{len(tks)} 檔到最新")

def main():
    eps = fetch_transcripts()
    news = new_episodes(eps)
    if news:
        log(f"發現 {len(news)} 集新的: {news}")
        if not os.environ.get("ANTHROPIC_API_KEY") and not (ROOT / ".env").exists():
            log("警告: 無 API key, 跳過抽取(只更新線型)")
        else:
            import extract_llm
            extract_llm.main([str(n) for n in news])
    else:
        log("沒有新集數, 只更新線型")
    update_prices()
    import importlib, watchlist, dashboard, combine
    for m in (watchlist, dashboard, combine):
        importlib.reload(m)
    combine.main()
    docs = ROOT / "docs"; docs.mkdir(exist_ok=True)
    shutil.copy(ROOT / "output" / "index.html", docs / "index.html")
    log(f"完成: docs/index.html 已更新 ({dt.datetime.now():%Y-%m-%d %H:%M})")

if __name__ == "__main__":
    main()
