"""公式の入手先から、日本銀行・内閣府・財務省のデータを data/raw/ に取得する。

このリポジトリは生データを含みません。実行すると、次を公式サイトから取得して保存します。
- 日本銀行「時系列統計データ検索サイト」API（認証不要）：国際収支、ドル円、国内企業物価指数、企業向けサービス価格指数
- 内閣府「国民経済計算」2024年度年次推計の Excel
- 財務省 財務総合政策研究所「純粋持株会社を除く経常利益」の Excel（検算用）

法人企業統計（e-Stat）は、画面からダウンロードしたCSVを使います（README参照）。

実行: python fetch_data.py
取得したデータの指紋を、記事執筆時（2026-10-10）の値と比べて表示します。
統計は改定されるため、不一致でも誤りとは限りません（数値が記事と変わる可能性があります）。
"""
import csv
import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
UA = {"User-Agent": "Mozilla/5.0 (compatible; reproduction-script)"}

BOJ_API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode?"
BOJ_FILES = {
    "boj_bp_direct_investment_monthly.csv": dict(
        db="BP01", startDate="199601", endDate="202608",
        code="BPBP6JYNPIN,BPBP6JYNPIC,BPBP6JYNPIC2,BPBP6JYNPIC21,BPBP6JYNPID21,BPBP6JYNPIC211,"
             "BPBP6JYNPIC2111,BPBP6JYNPIC2112,BPBP6JYNPIC212,BPBP6JYNPIC22"),
    "boj_fx_usdjpy_monthly_avg.csv": dict(db="FM08", startDate="199601", endDate="202609", code="FXERM07"),
    "boj_cgpi_monthly.csv": dict(db="PR01", startDate="198001", endDate="202608", code="PRCG20_2200000000"),
    "boj_sppi_monthly.csv": dict(db="PR02", startDate="198501", endDate="202608", code="PRCS20_5200000000"),
}
URL_FILES = {
    "2024i2_jp.xlsx": "https://www.esri.cao.go.jp/jp/sna/data/data_list/kakuhou/files/2024/tables/2024i2_jp.xlsx",
    "keitunenenpo.xlsx": "https://www.mof.go.jp/pri/reference/ssc/results/keitunenenpo.xlsx",
}
# 記事執筆時（2026-10-10）に取得したデータの指紋（参考：統計の改定で変わることがある）
# Excelはファイルの SHA-256。日銀のCSVは、取得時刻などが毎回変わるため、
# 「系列コード・時点・値」だけから作った指紋で比べる。
REF_HASH = {
    "boj_bp_direct_investment_monthly.csv": "44b69115da8164e37201d293acadaede182e87fc02c22d6a38f7c1e46c67b31f",
    "boj_fx_usdjpy_monthly_avg.csv": "4e7311999091cf57a63524411f38609c64bf19c713285fc9afafbeb9cca8b237",
    "boj_cgpi_monthly.csv": "59a1e0925cfbf821224b097c619cb1ca26bbed2280dd8118e4b31cb3c89e06b8",
    "boj_sppi_monthly.csv": "734089b1c8859910f53258bfe883f4311dc64651b20c9335537d9f50f4e28e09",
    "2024i2_jp.xlsx": "81090bee1c247daa705072a5404a522298cc5e300976d497dd38ef3c075b3914",
    "keitunenenpo.xlsx": "97dff1553ef368d263529f6f07e8c96adee89fd3962424682b825c8c99e8c19e",
}


def fingerprint(name, data):
    if name.endswith(".csv"):
        lines = data.decode("cp932").splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("SERIES_CODE,"))
        h = hashlib.sha256()
        for r in csv.reader(lines[start + 1:]):
            h.update(("|".join([r[0], r[6], r[7]]) + "\n").encode())
        return h.hexdigest()
    return hashlib.sha256(data).hexdigest()


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    jobs = []
    for name, params in BOJ_FILES.items():
        q = urllib.parse.urlencode({"format": "csv", "lang": "jp", **params}, safe=",")
        jobs.append((name, BOJ_API + q))
    for name, url in URL_FILES.items():
        jobs.append((name, url))
    ok = True
    for name, url in jobs:
        try:
            data = get(url)
        except Exception as e:  # noqa: BLE001
            print(f"NG  {name}: 取得に失敗しました（{e}）\n    {url}")
            ok = False
            continue
        (RAW / name).write_bytes(data)
        digest = fingerprint(name, data)
        note = "（記事執筆時と一致）" if digest == REF_HASH[name] else "（記事執筆時の値と異なる：統計の改定の可能性）"
        print(f"OK  {name}  {len(data):,} bytes  sha256={digest[:12]}…{note}")
    if not ok:
        sys.exit("一部のデータが取得できませんでした。")


if __name__ == "__main__":
    main()
