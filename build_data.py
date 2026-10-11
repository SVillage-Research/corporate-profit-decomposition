"""企業の最高益の分解：取得済み生データから分析用CSVを作る。

入力は data/raw/ にある次のファイル。出力は data/ に書く。パスはこのファイルからの相対。

- houjin_table1_all_ex_fin_FY1980_2025.csv   法人企業統計 全産業（除く金融保険業）・全規模・年度
- houjin_table1_pure_holding_FY2009_2025.csv  同 純粋持株会社
- keitunenenpo.xlsx                           財務省公表の「純粋持株会社を除く経常利益」（検算用）
- boj_bp_direct_investment_monthly.csv        日銀 国際収支統計(6版) 月次（億円、Shift_JIS）
- boj_fx_usdjpy_monthly_avg.csv               日銀 東京市場ドル・円 17時 月中平均（Shift_JIS）
- 2024i2_jp.xlsx                              内閣府 国民経済計算 2024年度年次推計 非金融法人企業

実行: python build_data.py
"""
import csv
import hashlib
import io
import json
import unicodedata
from pathlib import Path

import openpyxl
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
OUT = HERE / "data"


def read_boj(path):
    text = Path(path).read_bytes().decode("cp932")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("SERIES_CODE,"))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df["date"] = df["SURVEY_DATES"].astype(str)
    df["year"] = df["date"].str[:4].astype(int)
    df["month"] = df["date"].str[4:6].astype(int)
    df["fy"] = df["year"].where(df["month"] >= 4, df["year"] - 1)
    return df


# ---- 1. 国際収支（直接投資収益など）：暦年・年度に集計 ----
bp = read_boj(RAW / "boj_bp_direct_investment_monthly.csv")
names = {
    "BPBP6JYNPIN": "第一次所得収支_ネット",
    "BPBP6JYNPIC": "第一次所得_受取",
    "BPBP6JYNPIC2": "投資収益_受取",
    "BPBP6JYNPIC21": "直接投資収益_受取",
    "BPBP6JYNPID21": "直接投資収益_支払",
    "BPBP6JYNPIC211": "直接投資_出資所得_受取",
    "BPBP6JYNPIC2111": "直接投資_配当金配分済支店収益_受取",
    "BPBP6JYNPIC2112": "直接投資_再投資収益_受取",
    "BPBP6JYNPIC212": "直接投資_利子所得_受取",
    "BPBP6JYNPIC22": "証券投資収益_受取",
}
bp["系列"] = bp["SERIES_CODE"].map(names)
bp["VALUES"] = pd.to_numeric(bp["VALUES"], errors="coerce")


def agg(df, key, months_needed=12):
    g = df.groupby([key, "系列"])["VALUES"].agg(["sum", "count"]).reset_index()
    g = g[g["count"] == months_needed]  # 12か月そろった年だけ
    return g.pivot(index=key, columns="系列", values="sum")[list(names.values())]


bp_fy = agg(bp, "fy")
bp_fy.index.name = "年度"
bp_fy.to_csv(OUT / "bop_fy_oku_yen.csv", encoding="utf-8-sig")
bp_cy = agg(bp, "year")
bp_cy.index.name = "暦年"
bp_cy.to_csv(OUT / "bop_cy_oku_yen.csv", encoding="utf-8-sig")

# ---- 2. 為替：ドル円 月中平均を年度・暦年平均に ----
fx = read_boj(RAW / "boj_fx_usdjpy_monthly_avg.csv")
fx["VALUES"] = pd.to_numeric(fx["VALUES"], errors="coerce")
fx_fy = fx.groupby("fy")["VALUES"].agg(["mean", "count"])
fx_fy = fx_fy[fx_fy["count"] == 12][["mean"]].rename(columns={"mean": "ドル円_年度平均"})
fx_fy.index.name = "年度"
fx_fy.round(4).to_csv(OUT / "usdjpy_fy_avg.csv", encoding="utf-8-sig")

# ---- 2b. 物価：国内企業物価指数（財）と企業向けサービス価格指数（サービス）の年度平均 ----
def fy_mean(path):
    df = read_boj(path)
    df["VALUES"] = pd.to_numeric(df["VALUES"], errors="coerce")
    g = df.groupby("fy")["VALUES"].agg(["mean", "count"])
    return g[g["count"] == 12]["mean"]


defl = pd.DataFrame({"国内企業物価指数_総平均": fy_mean(RAW / "boj_cgpi_monthly.csv"),
                     "企業向けサービス価格指数_総平均": fy_mean(RAW / "boj_sppi_monthly.csv")})
defl.index.name = "年度"
defl.round(4).to_csv(OUT / "deflators_fy.csv", encoding="utf-8-sig")

# ---- 3. SNA 非金融法人企業（暦年、10億円） ----
def sna_rows(path, sector):
    ws = openpyxl.load_workbook(path, data_only=True)["暦年（１）"]
    years = [c.value for c in ws[7][1:] if c.value is not None]
    want = {
        "営業余剰_純": "1.3",
        "営業余剰_総": "（再掲）営業余剰（総）",
        "固定資本減耗": "（控除）固定資本減耗",
        "財産所得_受取": "1.4",
        "利子_受取": None,
        "配当_受取": None,
        "海外直接投資再投資収益_受取": None,
        "財産所得_支払": "1.1",
        "第1次所得バランス_純": "1.2",
        "第1次所得バランス_総": "（再掲）第１次所得バランス（総）",
    }
    rows = {}
    section = None  # 受取側／支払側の見出し位置で（１）利子などを区別する
    for r in ws.iter_rows(min_row=8, values_only=True):
        label = unicodedata.normalize("NFKC", str(r[0] or "")).replace("　", "").replace(" ", "")
        if label.startswith("1.1"):
            section = "支払"
        elif label.startswith("1.4"):
            section = "受取"
        vals = list(r[1:1 + len(years)])
        if label.startswith("1.3"):
            rows["営業余剰_純"] = vals
        elif label.startswith("(再掲)営業余剰(総)"):
            rows["営業余剰_総"] = vals
        elif label.startswith("(控除)固定資本減耗") and "固定資本減耗" not in rows:
            rows["固定資本減耗"] = vals
        elif label.startswith("1.4"):
            rows["財産所得_受取"] = vals
        elif label.startswith("1.1"):
            rows["財産所得_支払"] = vals
        elif label.startswith("1.2"):
            rows["第1次所得バランス_純"] = vals
        elif label.startswith("(再掲)第1次所得バランス(総)"):
            rows["第1次所得バランス_総"] = vals
        elif section == "受取" and label.startswith("(1)利子"):
            rows["利子_受取"] = vals
        elif section == "受取" and label.startswith("a.配当"):
            rows["配当_受取"] = vals
        elif section == "受取" and label.startswith("(3)海外直接投資に関する再投資収益"):
            rows["海外直接投資再投資収益_受取"] = vals
        elif section == "支払" and label.startswith("(1)利子"):
            rows["利子_支払"] = vals
        elif section == "支払" and label.startswith("a.配当"):
            rows["配当_支払"] = vals
    df = pd.DataFrame(rows, index=[int(y) for y in years])
    df.index.name = "暦年"
    df.insert(0, "部門", sector)
    return df


sna_nf = sna_rows(RAW / "2024i2_jp.xlsx", "非金融法人企業")
sna_nf.to_csv(OUT / "sna_nonfin_corp_cy_10oku_yen.csv", encoding="utf-8-sig")

# ---- 4. 法人企業統計 ----
h = pd.read_csv(RAW / "houjin_table1_all_ex_fin_FY1980_2025.csv").set_index("年度")
ph = pd.read_csv(RAW / "houjin_table1_pure_holding_FY2009_2025.csv").set_index("年度")
# 恒等式：経常利益 = 営業利益 + 営業外収益 - 営業外費用
assert (h["営業利益"] + h["営業外収益"] - h["営業外費用"] - h["経常利益"]).abs().max() == 0
# 財務省公表値（純粋持株会社を除く経常利益）との突き合わせ
ws = openpyxl.load_workbook(RAW / "keitunenenpo.xlsx", data_only=True).active
mof = {}
for r in ws.iter_rows(values_only=True):
    if r[0] and str(r[0]).startswith(("平成", "令和")):
        s = unicodedata.normalize("NFKC", r[0]).replace("元", "1")
        n = int("".join(c for c in s if c.isdigit()))
        mof[1988 + n if s.startswith("平成") else 2018 + n] = (r[1] * 100, r[2] * 100, r[3] * 100)
diff = max(
    max(abs(v[0] - h.loc[y, "経常利益"]), abs(v[1] - ph.loc[y, "経常利益"])) for y, v in mof.items()
)
assert diff < 1, diff
print("財務省公表値との最大差（百万円）:", diff)

# ---- 5. 結合表（年度ベース） ----
m = h[["売上高", "営業利益", "営業外収益", "営業外費用", "経常利益", "支払利息等", "配当金計", "当期純利益"]].copy()
m = m.join(ph[["経常利益", "営業利益", "営業外収益"]].add_prefix("純粋持株会社_"))
m["経常利益_純粋持株会社を除く"] = m["経常利益"] - m["純粋持株会社_経常利益"].fillna(0)
m = m.join(bp_fy).join(fx_fy)
m.to_csv(OUT / "merged_fy_million_yen_and_oku_yen.csv", encoding="utf-8-sig")

# ---- 6. 取得元の記録（SHA-256付き） ----
def sha(p):
    p = Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


manifest = {
    "houjin_table1_all_ex_fin": {
        "file": "raw/houjin_table1_all_ex_fin_FY1980_2025.csv",
        "source": "法人企業統計調査 時系列データ 表1 金融業、保険業以外の業種（原数値、年度）。全産業（除く金融保険業）・全規模",
        "url": "https://www.e-stat.go.jp/dbview?sid=0003060791",
        "retrieved": "2026-10-10",
        "method": "e-Statの画面からダウンロードしたCSV（README参照）から parse_estat.py で作成。FY2025（2025年度）まで",
        "sha256": sha(RAW / "houjin_table1_all_ex_fin_FY1980_2025.csv"),
        "unit": "百万円（母集団は社、従業員は人）",
    },
    "houjin_table1_pure_holding": {
        "file": "raw/houjin_table1_pure_holding_FY2009_2025.csv",
        "source": "同表 業種=純粋持株会社・全規模",
        "url": "https://www.e-stat.go.jp/dbview?sid=0003060791",
        "retrieved": "2026-10-10",
        "sha256": sha(RAW / "houjin_table1_pure_holding_FY2009_2025.csv"),
        "unit": "百万円",
    },
    "houjin_value_added_all": {
        "file": "raw/houjin_table1_all_ex_fin_value_added_FY1980_2025.csv",
        "source": "同表 全産業（除く金融保険業）・全規模：付加価値と内訳（人件費、支払利息等、賃借料、租税公課、営業純益）、従業員数・役員数",
        "url": "https://www.e-stat.go.jp/dbview?sid=0003060791",
        "retrieved": "2026-10-10",
        "method": "e-Statの画面からダウンロードしたCSVから作成。付加価値＝人件費＋支払利息等＋動産・不動産賃借料＋租税公課＋営業純益が全年で成立（役員賞与はFY2006まで人件費に含まれない）",
        "sha256": sha(RAW / "houjin_table1_all_ex_fin_value_added_FY1980_2025.csv"),
        "unit": "百万円（人数は人）",
    },
    "houjin_value_added_10oku_plus": {
        "file": "raw/houjin_table1_capital_10oku_plus_value_added_FY1980_2025.csv",
        "source": "同表 資本金10億円以上（全産業・除く金融保険業）。10億円未満は全規模との差で求める",
        "url": "https://www.e-stat.go.jp/dbview?sid=0003060791",
        "retrieved": "2026-10-10",
        "sha256": sha(RAW / "houjin_table1_capital_10oku_plus_value_added_FY1980_2025.csv"),
        "unit": "百万円（人数は人）",
    },
    "boj_cgpi": {
        "file": "raw/boj_cgpi_monthly.csv",
        "source": "日本銀行 DB=PR01 PRCG20_2200000000 国内企業物価指数 総平均（2020年基準）月次",
        "url": "https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=csv&lang=jp&db=PR01&startDate=198001&endDate=202608&code=PRCG20_2200000000",
        "retrieved": "2026-10-10",
        "sha256": sha(RAW / "boj_cgpi_monthly.csv"),
        "unit": "2020年=100",
    },
    "boj_sppi": {
        "file": "raw/boj_sppi_monthly.csv",
        "source": "日本銀行 DB=PR02 PRCS20_5200000000 企業向けサービス価格指数 基本分類指数 総平均（2020年基準）月次",
        "url": "https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=csv&lang=jp&db=PR02&startDate=198501&endDate=202608&code=PRCS20_5200000000",
        "retrieved": "2026-10-10",
        "sha256": sha(RAW / "boj_sppi_monthly.csv"),
        "unit": "2020年=100",
    },
    "houjin_cost_structure": {
        "file": "raw/houjin_table1_all_ex_fin_cost_structure_FY1980_2025.csv",
        "source": "同表 全産業（除く金融保険業）・全規模：売上高、売上原価、販売費及び一般管理費、営業利益",
        "url": "https://www.e-stat.go.jp/dbview?sid=0003060791",
        "retrieved": "2026-10-10",
        "method": "画面上の表を抽出。列合計を画面側と突き合わせて確認。売上高−売上原価−販管費＝営業利益が全年で成立",
        "sha256": sha(RAW / "houjin_table1_all_ex_fin_cost_structure_FY1980_2025.csv"),
        "unit": "百万円",
    },
    "mof_keitunenenpo": {
        "file": "raw/keitunenenpo.xlsx",
        "source": "財務省 財務総合政策研究所『純粋持株会社を除く経常利益』（年度）",
        "url": "https://www.mof.go.jp/pri/reference/ssc/results/keitunenenpo.xlsx",
        "retrieved": "2026-10-10",
        "sha256": sha(RAW / "keitunenenpo.xlsx"),
        "unit": "億円",
    },
    "boj_bp": {
        "file": "raw/boj_bp_direct_investment_monthly.csv",
        "source": "日本銀行 時系列統計データ検索サイト（API）DB=BP01 国際収支統計（6版基準）月次、第一次所得関連",
        "url": "https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=csv&lang=jp&db=BP01&startDate=199601&endDate=202608&code=" + ",".join(names),
        "retrieved": "2026-10-10",
        "sha256": sha(RAW / "boj_bp_direct_investment_monthly.csv"),
        "unit": "億円",
    },
    "boj_fx": {
        "file": "raw/boj_fx_usdjpy_monthly_avg.csv",
        "source": "日本銀行 DB=FM08 FXERM07 東京市場ドル・円スポット17時時点／月中平均",
        "url": "https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=csv&lang=jp&db=FM08&startDate=199601&endDate=202609&code=FXERM07",
        "retrieved": "2026-10-10",
        "sha256": sha(RAW / "boj_fx_usdjpy_monthly_avg.csv"),
        "unit": "1ドルにつき円",
    },
    "sna_nonfin_corp": {
        "file": "raw/2024i2_jp.xlsx",
        "source": "内閣府 国民経済計算 2024年度年次推計（2020年基準）制度部門別所得支出勘定 非金融法人企業",
        "url": "https://www.esri.cao.go.jp/jp/sna/data/data_list/kakuhou/files/2024/tables/2024i2_jp.xlsx",
        "retrieved": "2026-09-09（交易損失②で取得、SHA-256一致を確認して複製）",
        "sha256": sha(RAW / "2024i2_jp.xlsx"),
        "unit": "10億円",
    },
}
(OUT / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
print("done:", sorted(p.name for p in OUT.glob("*.csv")))
