"""看多子集回測 — 只取 LLM 判定 stance=bull 的標的, 全樣本 × 分多空頭.
對照組: 全提及(fullrun.json)。看「過濾語氣」是否把訊號從雜訊救出來。
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fullrun import prices, fwd, regime, BENCH, LAG, HORIZONS, tab
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

def build(stances):
    rows = []
    seen = set()
    for m in json.load(open(ROOT / "data" / "llm_picks.json")):
        if m.get("stance") not in stances or not m.get("ticker") or m.get("market") not in ("US", "TW"):
            continue
        key = (m["ep"], m["ticker"])
        if key in seen:
            continue
        seen.add(key)
        s = prices(m["ticker"]); b = prices(BENCH[m["market"]])
        if s is None or b is None:
            continue
        lag = LAG[m["market"]]
        edate, r = fwd(s, m["date"], lag)
        if r is None:
            continue
        _, br = fwd(b, m["date"], lag)
        row = {**m, "regime": regime(m["market"], m["date"])}
        for h in HORIZONS:
            row[f"r{h}"] = r[h]
            row[f"a{h}"] = (r[h] - br[h]) if (br and r[h] is not None and br[h] is not None) else None
        rows.append(row)
    return rows

if __name__ == "__main__":
    bull = build({"bull"})
    bear = build({"bear"})
    json.dump([{k:(round(v,2) if isinstance(v,float) else v) for k,v in r.items()} for r in bull],
              open(ROOT/"output"/"bullrun.json","w"), ensure_ascii=False)
    print(f"=== 看多子集: {len(bull)} 筆 (美股{sum(1 for r in bull if r['market']=='US')}/台股{sum(1 for r in bull if r['market']=='TW')}) ===")
    for mk in ("US", "TW"):
        sub=[r for r in bull if r["market"]==mk]
        nm="美股(對QQQ)" if mk=="US" else "台股(對0050)"
        print("\n"+"="*60); print(f"### {nm} 看多")
        tab(sub, f"{nm} 看多·全行情")
        for reg in ("多頭","空頭"):
            rs=[r for r in sub if r["regime"]==reg]
            if rs: tab(rs, f"{nm} 看多·只看【{reg}】")
    # 對照: 看空子集表現(他看壞的, 應該較差才合理)
    print("\n"+"="*60); print("### 對照組:他【看空】的標的(全市場)")
    tab([r for r in bear], f"看空全部 n={len(bear)}")
