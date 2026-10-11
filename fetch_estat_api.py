"""e-Stat API から法人企業統計 表1を取得し、data/estat/ に3つのCSVを作る（parse_estat.py が読む形式）。

必要なもの：e-Stat の appId（無料。https://www.e-stat.go.jp/api/ で利用登録して取得）。
appId は、環境変数 ESTAT_APP_ID に入れるか、実行時の入力（画面に表示されません）で渡します。
appId はファイルに保存しません。他人に渡したり、リポジトリに入れたりしないでください。

取得するのは「法人企業統計調査 時系列データ 表1 金融業、保険業以外の業種（原数値）」（年度）です。
  statsDataId = 0003060791（e-Statの統計表ID。画面のURL dbview?sid=0003060791 と同じ）
業種と規模の組み合わせ3つ：
  estat_all_ex_fin_all_size.csv   全産業（除く金融保険業）・全規模
  estat_pure_holding_all_size.csv 純粋持株会社・全規模
  estat_all_ex_fin_10oku_plus.csv 全産業（除く金融保険業）・資本金10億円以上

実行: python fetch_estat_api.py
取得後、記事の値（2025年度・全産業・全規模の経常利益など）と照合して表示します。
統計が改定されていれば、不一致になることがあります。
"""
import csv
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ESTAT = HERE / "data" / "estat"

API = "https://api.e-stat.go.jp/rest/3.0/app/json/"
STATS_DATA_ID = "0003060791"
SELECTIONS = {
    "estat_all_ex_fin_all_size.csv": ("全産業（除く金融保険業）", "全規模"),
    "estat_pure_holding_all_size.csv": ("純粋持株会社", "全規模"),
    "estat_all_ex_fin_10oku_plus.csv": ("全産業（除く金融保険業）", "10億円以上"),
}
# 記事執筆時（2026-10-10）の値（百万円）。全産業（除く金融保険業）・全規模・2025年度
CHECK_2025 = {"経常利益": 124831342, "売上高": 1720255968, "付加価値": 373670064}


def norm(s):
    s = re.sub(r"[\s　]+", "", str(s))
    return s.replace("(", "（").replace(")", "）")


def call(app_id, method, **params):
    q = urllib.parse.urlencode({"appId": app_id, "lang": "J", **params})
    url = f"{API}{method}?{q}"
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"e-Stat API のエラー（HTTP {e.code}）。appId が正しいか確認してください。")
    except urllib.error.URLError as e:
        sys.exit(f"e-Stat API に接続できません（{e.reason}）。")


def as_list(x):
    return x if isinstance(x, list) else [x]


def parse_meta(meta):
    """軸（調査項目・業種・規模）と時間軸を、名前から探す。"""
    objs = as_list(meta["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"])
    axes = {}
    for o in objs:
        name = norm(o["@name"])
        classes = {c["@code"]: c["@name"] for c in as_list(o["CLASS"])}
        if o["@id"] == "time":
            axes["time"] = (o["@id"], classes)
        elif name.startswith("業種"):
            axes["industry"] = (o["@id"], classes)
        elif name.startswith("規模"):
            axes["size"] = (o["@id"], classes)
        elif name.startswith("調査項目") or name.startswith("項目"):
            axes["item"] = (o["@id"], classes)
    missing = [k for k in ("time", "industry", "size", "item") if k not in axes]
    if missing:
        sys.exit(f"統計表の軸を特定できませんでした: {missing}。e-Statの統計表の構成が変わった可能性があります。")
    return axes


def code_of(classes, wanted):
    hits = [c for c, n in classes.items() if norm(n) == norm(wanted)]
    if not hits:
        sys.exit(f"「{wanted}」が見つかりません。候補: {[n for n in classes.values()][:15]}…")
    return hits[0]


def fetch_one(app_id, axes, industry, size):
    ind_id, ind_cls = axes["industry"]
    size_id, size_cls = axes["size"]
    params = {
        "statsDataId": STATS_DATA_ID,
        "cd" + ind_id[0].upper() + ind_id[1:]: code_of(ind_cls, industry),
        "cd" + size_id[0].upper() + size_id[1:]: code_of(size_cls, size),
        "metaGetFlg": "N", "cntGetFlg": "N", "limit": "100000",
    }
    rows = []
    start = None
    while True:
        p = dict(params)
        if start:
            p["startPosition"] = start
        d = call(app_id, "getStatsData", **p)
        sd = d["GET_STATS_DATA"]
        if sd["RESULT"].get("STATUS") not in (0, "0"):
            sys.exit(f"e-Stat API: {sd['RESULT'].get('ERROR_MSG')}")
        rows += as_list(sd["STATISTICAL_DATA"]["DATA_INF"]["VALUE"])
        nxt = sd["STATISTICAL_DATA"]["RESULT_INF"].get("NEXT_KEY")
        if not nxt:
            break
        start = nxt
    return rows


def write_csv(path, rows, axes):
    item_id, item_cls = axes["item"]
    time_cls = axes["time"][1]
    table = {}
    for v in rows:
        year = re.match(r"\d{4}", time_cls[v["@time"]])
        if not year:
            continue
        table.setdefault(int(year.group()), {})[v["@" + item_id]] = v.get("$", "")
    item_codes = list(item_cls)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([""] + [item_cls[c] for c in item_codes])
        for y in sorted(table):
            w.writerow([f"{y}年度"] + [table[y].get(c, "") for c in item_codes])
    return table, item_cls


def main():
    app_id = os.environ.get("ESTAT_APP_ID") or getpass.getpass("e-Stat の appId（入力は表示されません）: ").strip()
    if not app_id:
        sys.exit("appId がありません。")
    ESTAT.mkdir(parents=True, exist_ok=True)
    meta = call(app_id, "getMetaInfo", statsDataId=STATS_DATA_ID)
    axes = parse_meta(meta)
    for fname, (industry, size) in SELECTIONS.items():
        rows = fetch_one(app_id, axes, industry, size)
        table, item_cls = write_csv(ESTAT / fname, rows, axes)
        print(f"OK  {fname}: {len(table)}年度、{len(item_cls)}項目（{industry}・{size}）")
        if fname == "estat_all_ex_fin_all_size.csv":
            names = {norm(re.sub(r"【[^】]*】|[（(]当期末[）)]", "", n)): c for c, n in item_cls.items()}
            for item, expected in CHECK_2025.items():
                code = names.get(item)
                got = table.get(2025, {}).get(code, "")
                ok = str(got).replace(",", "") == str(expected)
                print(f"  {'OK ' if ok else 'NG '} 2025年度の{item}: {got}（記事執筆時 {expected:,}）")


if __name__ == "__main__":
    main()
