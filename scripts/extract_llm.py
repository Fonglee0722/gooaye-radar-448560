"""LLM 抽取器 (信號A核心) — 用 Claude 從逐字稿抽結構化標的清單.

讀 .env 的 ANTHROPIC_API_KEY。對每集輸出 {name,market,ticker,kind,stance,conviction,reason}。
台股代號用 ticker_map 依名稱校正(較準); 美股用模型給的代號。
用法: python scripts/extract_llm.py 563 580 597 641 615   (給集號)
      python scripts/extract_llm.py ALL                    (全部)
輸出: data/llm_picks.json (累加, 以 ep 去重覆蓋)
"""
import json, os, sys, re, time
from pathlib import Path
import anthropic

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MODEL = "claude-sonnet-4-6"

def load_key():
    if os.environ.get("ANTHROPIC_API_KEY"):        # CI: GitHub Secret
        return os.environ["ANTHROPIC_API_KEY"]
    env = ROOT / ".env"                             # 本機: .env 檔
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("ANTHROPIC_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("無 ANTHROPIC_API_KEY")

ticker_map = json.load(open(DATA / "ticker_map.json"))
# 反查: 4碼代號 -> 完整 yfinance 代號 (取第一個非權證對應)
code_to_yf = {}
for nm, full in ticker_map.items():
    if any(w in nm for w in ("購", "售", "牛", "熊")):
        continue
    code_to_yf.setdefault(full.split(".")[0], full)

def resolve_tw(name, number):
    """台股代號解析: 先用名稱查權威表(最可靠), 再用模型號碼配權威後綴, 最後猜.TW。"""
    for cand in (name, (name or "").replace("*", "").replace("＊", ""), f"{name}-KY"):
        if cand in ticker_map:
            return ticker_map[cand]
    if number:
        return code_to_yf.get(str(number).strip(), f"{str(number).strip()}.TW")
    return None

SYS = """你是台股與美股投資分析助理。輸入是財經 podcast《股癌》(主持人謝孟恭)單集逐字稿。
你的任務:抽取他在本集真正談到的「投資標的」。

規則:
- 只抽真正的投資標的:個股、ETF、或明確的產業族群/概念題材(如「光通訊」「記憶體」「無人機」)。
- 忽略:贊助商廣告(節目開頭的業配)、書籍、電影、餐廳、遊戲、卡牌、生活閒聊、聽眾的生日祝福。
- stance 一定要判斷「謝孟恭本人在本集對該標的的態度」:
    bull = 他看好/有買/抱著/喜歡/叫大家注意正面/認為會漲
    bear = 他看壞/賣掉/不喜歡/當作反例/認為會跌/警示
    neutral = 只是順口提到、客觀描述產業、或聽眾問他但他沒明確表態
- conviction:他講得多用力 high/med/low。
- 同一標的本集只輸出一次,取他最主要的態度。
- ticker:台股填4碼數字(如 2330),美股填美股代號(如 NVDA),產業族群或不確定填 null。

只輸出 JSON 陣列,每個元素:
{"name":"他口中的講法","market":"US|TW|OTHER","ticker":"代號或null","kind":"個股|ETF|族群","stance":"bull|bear|neutral","conviction":"high|med|low","reason":"12字內理由"}
不要輸出 JSON 以外的任何文字。"""

def extract_one(client, ep):
    msg = client.messages.create(
        model=MODEL, max_tokens=3000, system=SYS,
        messages=[{"role": "user", "content": f"EP{ep['n']} 逐字稿:\n\n{ep['tx']}"}],
    )
    txt = msg.content[0].text.strip()
    m = re.search(r"\[.*\]", txt, re.S)
    items = json.loads(m.group(0) if m else txt)
    out = []
    for it in items:
        tk = it.get("ticker")
        mk = it.get("market")
        if mk == "TW":
            tk = resolve_tw(it.get("name"), tk)  # 名稱優先, 權威後綴
        out.append({"ep": ep["n"], "date": ep["d"], **it, "ticker": tk})
    return out, (msg.usage.input_tokens, msg.usage.output_tokens)

def main(which):
    key = load_key()
    client = anthropic.Anthropic(api_key=key)
    eps = {e["n"]: e for e in json.load(open(DATA / "transcripts.json"))}
    limit = None
    if which and which[0] == "ALL":
        targets = sorted(eps)
        if len(which) > 1:  # ALL <N> = 本次最多抽 N 個新集
            limit = int(which[1])
    else:
        targets = [int(x) for x in which]
    fp = DATA / "llm_picks.json"
    existing = {}
    if fp.exists():
        for r in json.load(open(fp)):
            existing.setdefault(r["ep"], []).append(r)
    tin = tout = 0
    done = 0
    new_done = 0
    for i, n in enumerate(targets):
        if n in existing and existing[n]:
            done += 1
            continue  # 已抽過, 跳過(可續跑)
        if limit is not None and new_done >= limit:
            break  # 本次限量已達, 乾淨結束
        new_done += 1
        try:
            rows, (ti, to) = extract_one(client, eps[n])
            existing[n] = rows
            tin += ti; tout += to
            print(f"  EP{n} ({eps[n]['d']}) → {len(rows)}個標的  "
                  f"[in {ti} out {to} tok]", flush=True)
        except Exception as e:
            print(f"  EP{n} 失敗: {e}", flush=True)
        json.dump([r for rs in existing.values() for r in rs],  # 每集即存, 隨時可砍
                  open(fp, "w"), ensure_ascii=False, indent=1)
        time.sleep(0.2)
    print(f"(跳過已抽 {done} 集)")
    flat = [r for rows in existing.values() for r in rows]
    json.dump(flat, open(fp, "w"), ensure_ascii=False, indent=1)
    # 成本估算 (Sonnet: $3/M in, $15/M out)
    cost = tin/1e6*3 + tout/1e6*15
    print(f"\n本次 {len(targets)} 集: 輸入 {tin:,} / 輸出 {tout:,} tokens  ≈ ${cost:.3f}")
    print(f"推估全671集成本 ≈ ${cost/max(len(targets),1)*671:.1f}")
    print(f"已寫入 {fp} (累計 {len(flat)} 筆)")

if __name__ == "__main__":
    main(sys.argv[1:] or ["563", "580", "597", "641", "615"])
