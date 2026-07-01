"""字典比對抽取器 (無需API) — 掃全部逐字稿, 抓出每集提到的台股/美股標的.

產出 data/all_mentions.json: [{ep,date,name,ticker,market,count}]
注意: 只判斷「有沒有提到」, 不判斷看多/看空(那步留給LLM)。stance 一律 'mention'。
台股名稱來自 ticker_map(過濾權證/雜訊), 美股來自 us_names.json。
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ticker_map = json.load(open(DATA / "ticker_map.json"))
us_names = json.load(open(DATA / "us_names.json"))

# 2字台股名常撞日常用語。策略: 2字名「只」收白名單; 3字以上收(扣黑名單)。
# 白名單 = 股癌常談、且名稱無歧義的2字個股/ETF。
TW_WHITELIST_2 = {
    "鴻海", "廣達", "緯創", "緯穎", "智邦", "川湖", "奇鋐", "健鼎", "欣興", "景碩",
    "旺宏", "華邦", "聯電", "台達", "仁寶", "技嘉", "微星", "華碩", "和碩", "群創",
    "友達", "國巨", "世芯", "聯茂", "台燿", "定穎", "博智", "嘉澤", "貿聯", "信驊",
    "祥碩", "瑞昱", "聯詠", "矽創", "力旺", "超豐", "頎邦", "南電", "台郡", "臻鼎",
    "健策", "雙鴻", "建準", "泰碩", "力致", "元太", "亞光", "穩懋", "全新", "聯亞",
    "光聖", "聯鈞", "上詮", "光環", "前鼎", "創意", "晶豪", "群聯", "鈺創", "南亞科",
    "京元", "智原", "愛普", "緯軟", "神盾", "義隆", "凌通", "新唐", "盛群", "九齊",
    "可成", "鎧勝", "雷虎", "漢翔", "經緯", "亞創", "寶成", "豐泰",
    "矽格", "同欣", "精測", "穎崴", "旺矽", "聯鈞", "華星", "波若", "立積", "穩村",
    "台表科", "中砂", "崇越", "弘塑", "辛耘", "家登", "帆宣", "亞翔", "聖暉", "漢唐",
}
TW_BLOCK = {
    "統一", "中華", "全家", "大同", "國泰", "聯合", "中央", "第一", "台灣", "中國",
    "聯強", "豐興", "美時", "好樂迪", "全國", "大成", "新光", "永豐", "合庫", "世界",
    "中信", "遠東", "中橡", "正常", "南亞", "和成", "三商", "大江", "美亞", "光隆",
    "達新", "勤美", "東元", "中華電", "其他", "數字", "幸福", "互動", "進階", "動力",
    "巨大", "三星", "合一", "安心", "信大", "聯發", "信音", "互盛", "宏全", "大學",
    "全家福", "高科", "美食", "comfort", "大方", "大宇", "新天地", "六福", "晶華",
    "大量", "全新", "創意", "台灣大", "台灣大哥大", "亞創",
}

def build_tw_lookup():
    """過濾後的 台股名稱->代號。去權證、去過短、去黑名單、補-KY別名。"""
    lut = {}
    for name, code in ticker_map.items():
        if any(w in name for w in ("購", "售", "牛", "熊", "權證")):
            continue
        base = code.split(".")[0]
        # 只留 4 碼個股 與 00開頭ETF
        if not (len(base) == 4 and base[0] != "0") and not base.startswith("00"):
            continue
        if name in TW_BLOCK or len(name) < 2:
            continue
        if len(name) == 2 and name not in TW_WHITELIST_2:
            continue
        lut[name] = code
        alias = name.replace("-KY", "").replace("＊", "").replace("*", "")
        if alias != name and len(alias) >= 3 and alias not in TW_BLOCK:
            lut.setdefault(alias, code)
    return lut

def scan():
    tw = build_tw_lookup()
    eps = json.load(open(DATA / "transcripts.json"))
    out = []
    for e in eps:
        tx = e["tx"]
        seen = {}  # ticker -> (name, count)
        # 台股
        for name, code in tw.items():
            c = tx.count(name)
            if c:
                # 同代號多別名取最長名稱
                if code not in seen or len(name) > len(seen[code][0]):
                    seen[code] = (name, max(c, seen.get(code, ("", 0))[1]))
        for code, (name, c) in seen.items():
            out.append({"ep": e["n"], "date": e["d"], "name": name,
                        "ticker": code, "market": "TW", "count": c, "stance": "mention"})
        # 美股
        us_seen = {}
        for name, tk in us_names.items():
            c = len(re.findall(re.escape(name), tx, re.IGNORECASE)) if name.isascii() else tx.count(name)
            if c:
                us_seen[tk] = us_seen.get(tk, 0) + c
        for tk, c in us_seen.items():
            disp = next((n for n, t in us_names.items() if t == tk and not n.isascii()), tk)
            out.append({"ep": e["n"], "date": e["d"], "name": disp,
                        "ticker": tk, "market": "US", "count": c, "stance": "mention"})
    return out, tw

if __name__ == "__main__":
    mentions, tw = scan()
    json.dump(mentions, open(DATA / "all_mentions.json", "w"), ensure_ascii=False)
    print(f"台股字典(過濾後): {len(tw)} 檔")
    print(f"總提及數: {len(mentions)}  (台股{sum(1 for m in mentions if m['market']=='TW')} / 美股{sum(1 for m in mentions if m['market']=='US')})")
    print(f"涵蓋集數: {len(set(m['ep'] for m in mentions))} / 671")
    print(f"不重複台股: {len(set(m['ticker'] for m in mentions if m['market']=='TW'))}  美股: {len(set(m['ticker'] for m in mentions if m['market']=='US'))}")
    # 最常被提到的(檢查誤判用)
    from collections import Counter
    cnt = Counter()
    for m in mentions:
        cnt[(m["name"], m["ticker"])] += 1
    print("\n最常出現的30個(跨集出現次數, 用來抓誤判):")
    for (nm, tk), c in cnt.most_common(30):
        print(f"  {c:>3}集  {nm} ({tk})")
