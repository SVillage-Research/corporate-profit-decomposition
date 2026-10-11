"""企業の最高益の分解。build_data.py の出力から、記事の数値・図の元データを計算する。

実行: python analyze.py   （先に build_data.py を実行しておく）
出力: data/decomposition.csv, data/fx_counterfactual.csv, data/sna_vs_houjin.csv, data/metrics.json
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
D = HERE / "data"
RAW = D / "raw"
MIL = 1e6  # 百万円 -> 兆円

m = pd.read_csv(D / "merged_fy_million_yen_and_oku_yen.csv", index_col=0)
h = pd.read_csv(RAW / "houjin_table1_all_ex_fin_FY1980_2025.csv").set_index("年度")
ph = pd.read_csv(RAW / "houjin_table1_pure_holding_FY2009_2025.csv").set_index("年度")
sna = pd.read_csv(D / "sna_nonfin_corp_cy_10oku_yen.csv", index_col=0)

BASE, LAST = 2012, 2025
metrics = {"base_year": BASE, "last_year": LAST}


def decomp(df, a, b):
    d = df.loc[b] - df.loc[a]
    tot = d["経常利益"]
    out = {
        "経常利益_始点_兆円": df.loc[a, "経常利益"] / MIL,
        "経常利益_終点_兆円": df.loc[b, "経常利益"] / MIL,
        "増分_兆円": tot / MIL,
        "営業利益_兆円": d["営業利益"] / MIL,
        "営業外収益_兆円": d["営業外収益"] / MIL,
        "営業外費用の増加_兆円": d["営業外費用"] / MIL,  # 経常利益から差し引く向き
    }
    out["営業利益_割合"] = d["営業利益"] / tot
    out["営業外収益_割合"] = d["営業外収益"] / tot
    out["営業外費用_割合"] = -d["営業外費用"] / tot
    assert abs(d["営業利益"] + d["営業外収益"] - d["営業外費用"] - tot) < 1
    return out


# ---- 1. 経常利益の増分の分解（全産業・除く金融保険業） ----
rows = {}
for a, b in [(2012, 2025), (2012, 2024), (2000, 2025), (2013, 2025)]:
    rows[f"{a}->{b}"] = decomp(h, a, b)
# 純粋持株会社を除く（営業利益・営業外損益も除ける。FY2009〜）
hx = h.loc[ph.index, ["営業利益", "営業外収益", "営業外費用", "経常利益"]] - ph[["営業利益", "営業外収益", "営業外費用", "経常利益"]]
for a, b in [(2012, 2025)]:
    rows[f"{a}->{b}_持株会社除く"] = decomp(hx, a, b)
metrics["decomposition"] = rows
pd.DataFrame(rows).T.to_csv(D / "decomposition.csv", encoding="utf-8-sig")

# ---- 2. 営業利益の増分：売上高の増加 と 利益率の上昇 ----
s0, s1 = h.loc[BASE, "売上高"], h.loc[LAST, "売上高"]
m0, m1 = h.loc[BASE, "営業利益"] / s0, h.loc[LAST, "営業利益"] / s1
sales_eff = (s1 - s0) * m0
margin_eff = s1 * (m1 - m0)
assert abs(sales_eff + margin_eff - (h.loc[LAST, "営業利益"] - h.loc[BASE, "営業利益"])) < 1
metrics["operating_profit_split"] = {
    "売上高_始点_兆円": s0 / MIL, "売上高_終点_兆円": s1 / MIL, "売上高_増加率": s1 / s0 - 1,
    "営業利益率_始点": m0, "営業利益率_終点": m1,
    "売上増の効果_兆円": sales_eff / MIL, "利益率上昇の効果_兆円": margin_eff / MIL,
    "利益率上昇の割合": margin_eff / (sales_eff + margin_eff),
}
# 分け方は計算の順序で変わる。売上を先に見る（始点の利益率で評価）／利益率を先に見る（始点の売上で評価）の二通りと、その平均
_dS, _dm = s1 - s0, m1 - m0
_tot = h.loc[LAST, "営業利益"] - h.loc[BASE, "営業利益"]
metrics["operating_profit_split"].update({
    "売上高の増加倍率": s1 / s0, "営業利益率の上昇倍率": m1 / m0, "営業利益の増加倍率": h.loc[LAST, "営業利益"] / h.loc[BASE, "営業利益"],
    "売上増の効果_始点の利益率で評価_兆円": _dS * m0 / MIL, "売上増の効果_終点の利益率で評価_兆円": _dS * m1 / MIL,
    "利益率上昇の効果_始点の売上で評価_兆円": s0 * _dm / MIL, "利益率上昇の効果_終点の売上で評価_兆円": s1 * _dm / MIL,
    "交差項_兆円": _dS * _dm / MIL,
    "利益率上昇の割合_下限": s0 * _dm / _tot, "利益率上昇の割合_上限": s1 * _dm / _tot,
    "売上増の効果_平均_兆円": (_dS * m0 + _dS * m1) / 2 / MIL, "利益率上昇の効果_平均_兆円": (s0 * _dm + s1 * _dm) / 2 / MIL,
    "売上増の割合_平均": (_dS * m0 + _dS * m1) / 2 / _tot, "利益率上昇の割合_平均": (s0 * _dm + s1 * _dm) / 2 / _tot,
})
# 参考：営業利益率の推移
metrics["営業利益率_系列"] = (h["営業利益"] / h["売上高"]).round(5).to_dict()

# ---- 3. 営業外収益と国際収支（直接投資収益） ----
bp = m[["直接投資収益_受取", "直接投資_配当金配分済支店収益_受取", "直接投資_再投資収益_受取"]] / 1e4  # 億円 -> 兆円
nonop = m["営業外収益"] / MIL
metrics["nonop_vs_bop"] = {
    "営業外収益_増分_兆円": nonop[LAST] - nonop[BASE],
    "直接投資収益_受取_増分_兆円": bp.loc[LAST, "直接投資収益_受取"] - bp.loc[BASE, "直接投資収益_受取"],
    "うち配当金配分済支店収益_増分_兆円": bp.loc[LAST, "直接投資_配当金配分済支店収益_受取"] - bp.loc[BASE, "直接投資_配当金配分済支店収益_受取"],
    "うち再投資収益_増分_兆円": bp.loc[LAST, "直接投資_再投資収益_受取"] - bp.loc[BASE, "直接投資_再投資収益_受取"],
}
metrics["nonop_vs_bop"]["配当金配分済支店収益の増分／営業外収益の増分"] = (
    metrics["nonop_vs_bop"]["うち配当金配分済支店収益_増分_兆円"] / metrics["nonop_vs_bop"]["営業外収益_増分_兆円"]
)
# 参考：外国の株式・債券などからの配当・利子（証券投資収益）。金融機関・年金・家計などの受取を含み、法人企業統計の対象（金融業・保険業を除く企業）にどれだけ入るかは分からない
_sec = m["証券投資収益_受取"] / 1e4
metrics["nonop_vs_bop"]["証券投資収益_受取_2012_兆円"] = _sec[BASE]
metrics["nonop_vs_bop"]["証券投資収益_受取_2025_兆円"] = _sec[LAST]
metrics["nonop_vs_bop"]["証券投資収益_増分_兆円"] = _sec[LAST] - _sec[BASE]
metrics["nonop_vs_bop"]["直接投資の配当金・利子と証券投資収益の増分合計_兆円"] = (
    metrics["nonop_vs_bop"]["うち配当金配分済支店収益_増分_兆円"]
    + (bp_int := m["直接投資_利子所得_受取"] / 1e4)[LAST] - bp_int[BASE]
    + metrics["nonop_vs_bop"]["証券投資収益_増分_兆円"]
)

# ---- 4. 円安の寄与の目安（直接投資収益の全額がドル建てと仮定。上限の目安） ----
fx = m["ドル円_年度平均"]
cf = pd.DataFrame(index=m.index[m.index >= BASE])
cf["ドル円"] = fx
cf["直接投資収益_受取_兆円"] = bp["直接投資収益_受取"]
cf["円レート固定_兆円"] = cf["直接投資収益_受取_兆円"] * fx[BASE] / fx
cf["円安の寄与_兆円"] = cf["直接投資収益_受取_兆円"] - cf["円レート固定_兆円"]
cf = cf.dropna()
cf.round(4).to_csv(D / "fx_counterfactual.csv", encoding="utf-8-sig")
metrics["fx_counterfactual"] = {
    "基準レート_円": fx[BASE], "最終年レート_円": fx[LAST],
    "最終年の円安の寄与_兆円": cf.loc[LAST, "円安の寄与_兆円"],
    "経常利益増分に対する割合_上限": cf.loc[LAST, "円安の寄与_兆円"] / metrics["decomposition"]["2012->2025"]["増分_兆円"],
    "換算差の内訳_配当金配分済支店収益_兆円": bp.loc[LAST, "直接投資_配当金配分済支店収益_受取"] * (1 - fx[BASE] / fx[LAST]),
    "換算差の内訳_再投資収益_兆円": bp.loc[LAST, "直接投資_再投資収益_受取"] * (1 - fx[BASE] / fx[LAST]),
    "換算差の内訳_利子所得_兆円": (m["直接投資_利子所得_受取"] / 1e4)[LAST] * (1 - fx[BASE] / fx[LAST]),
    "反実仮想_2012年度の為替での2025年度の直接投資収益_兆円": cf.loc[LAST, "円レート固定_兆円"],
    "前提": "直接投資収益（受取）の全額がドル建てと仮定し、FY2012のレートに固定して換算し直した差（シナリオ計算で、上限ではない。ドル以外の通貨の動きは含まない）。再投資収益の分は法人単体の営業外収益に現れない。営業利益に含まれる輸出採算の円安効果は含まない",
}

# ---- 5. 支払利息等 ----
ie = h["支払利息等"] / MIL
metrics["interest"] = {
    "支払利息等_1995_兆円": ie[1995], "支払利息等_2000_兆円": ie[2000], "支払利息等_2012_兆円": ie[2012],
    "支払利息等_2021_兆円": ie[2021], "支払利息等_2025_兆円": ie[LAST],
    "支払利息等／営業利益_1995": h.loc[1995, "支払利息等"] / h.loc[1995, "営業利益"],
    "支払利息等／営業利益_2012": h.loc[2012, "支払利息等"] / h.loc[2012, "営業利益"],
    "支払利息等／営業利益_2025": h.loc[LAST, "支払利息等"] / h.loc[LAST, "営業利益"],
    "支払利息等の減少が経常利益を押し上げた額_1995から2012_兆円": ie[1995] - ie[2012],
    "支払利息等の増加が経常利益を押し下げた額_2012から2025_兆円": ie[LAST] - ie[2012],
}

# ---- 6. SNAとの突き合わせ（年度tを暦年tに対応させる。3か月ずれる） ----
yrs = [y for y in sna.index if y in h.index]
cmp_ = pd.DataFrame(index=yrs)
cmp_["法人企業統計_営業利益_兆円"] = h.loc[yrs, "営業利益"] / MIL
cmp_["法人企業統計_営業利益＋減価償却費_兆円"] = (h.loc[yrs, "営業利益"] + h.loc[yrs, "減価償却費計"]) / MIL
cmp_["SNA_営業余剰_総_兆円"] = sna.loc[yrs, "営業余剰_総"] / 1e3
cmp_["SNA_営業余剰_純_兆円"] = sna.loc[yrs, "営業余剰_純"] / 1e3
cmp_["SNA_固定資本減耗_兆円"] = sna.loc[yrs, "固定資本減耗"] / 1e3
cmp_["法人企業統計_減価償却費_兆円"] = h.loc[yrs, "減価償却費計"] / MIL
cmp_["SNA_財産所得_受取_兆円"] = sna.loc[yrs, "財産所得_受取"] / 1e3
cmp_.index.name = "年"
cmp_.round(3).to_csv(D / "sna_vs_houjin.csv", encoding="utf-8-sig")
c94, c24 = cmp_.loc[1994], cmp_.loc[2024]
metrics["sna_vs_houjin"] = {
    "法人_営業利益_1994": c94.iloc[0], "法人_営業利益_2024": c24.iloc[0],
    "SNA_営業余剰純_1994": c94["SNA_営業余剰_純_兆円"], "SNA_営業余剰純_2024": c24["SNA_営業余剰_純_兆円"],
    "SNA_営業余剰総_1994": c94["SNA_営業余剰_総_兆円"], "SNA_営業余剰総_2024": c24["SNA_営業余剰_総_兆円"],
    "SNA_固定資本減耗_1994": c94["SNA_固定資本減耗_兆円"], "SNA_固定資本減耗_2024": c24["SNA_固定資本減耗_兆円"],
    "法人_減価償却費_1994": c94["法人企業統計_減価償却費_兆円"], "法人_減価償却費_2024": c24["法人企業統計_減価償却費_兆円"],
}

# 純粋持株会社
metrics["pure_holding"] = {
    "経常利益シェア_2012": ph.loc[2012, "経常利益"] / h.loc[2012, "経常利益"],
    "経常利益シェア_2025": ph.loc[LAST, "経常利益"] / h.loc[LAST, "経常利益"],
}


# ---- 7. 付加価値の分配と労働分配率 ----
def load_va(name):
    v = pd.read_csv(RAW / name).set_index("年度").fillna(0)
    # 人件費：役員給与＋従業員給与＋従業員賞与＋福利厚生費。役員賞与はFY2007から含める（表の付加価値の内訳と一致させるため）
    v["人件費"] = v["役員給与"] + v["従業員給与"] + v["従業員賞与"] + v["福利厚生費"] + v["役員賞与"] * (v.index >= 2007)
    v["人数"] = v["期中平均従業員数_人"] + v["期中平均役員数_人"]
    return v


va_all = load_va("houjin_table1_all_ex_fin_value_added_FY1980_2025.csv")
va_big = load_va("houjin_table1_capital_10oku_plus_value_added_FY1980_2025.csv")
cols = ["付加価値", "人件費", "営業純益", "支払利息等", "動産不動産賃借料", "租税公課", "人数"]
va_small = va_all[cols] - va_big[cols]
for v in (va_all, va_big):  # 恒等式：付加価値＝人件費＋支払利息等＋賃借料＋租税公課＋営業純益
    res = v["付加価値"] - (v["人件費"] + v["支払利息等"] + v["動産不動産賃借料"] + v["租税公課"] + v["営業純益"])
    assert res.abs().max() == 0
    assert (v["営業利益"] - v["支払利息等"] - v["営業純益"]).abs().max() == 0

ls = pd.DataFrame({
    "全規模": va_all["人件費"] / va_all["付加価値"],
    "資本金10億円以上": va_big["人件費"] / va_big["付加価値"],
    "資本金10億円未満": va_small["人件費"] / va_small["付加価値"],
})
ls.index.name = "年度"
ls.round(5).to_csv(D / "labor_share_by_size.csv", encoding="utf-8-sig")

dist = {}
for a_, b_ in [(2012, 2025), (2000, 2025)]:
    d = va_all.loc[b_] - va_all.loc[a_]
    dist[f"{a_}->{b_}"] = {
        "付加価値_始点_兆円": va_all.loc[a_, "付加価値"] / MIL, "付加価値_終点_兆円": va_all.loc[b_, "付加価値"] / MIL,
        "付加価値_増分_兆円": d["付加価値"] / MIL,
        **{f"{k}_兆円": d[k] / MIL for k in ["人件費", "営業純益", "動産不動産賃借料", "租税公課", "支払利息等"]},
        **{f"{k}_割合": d[k] / d["付加価値"] for k in ["人件費", "営業純益", "動産不動産賃借料", "租税公課", "支払利息等"]},
        "労働分配率_始点": ls.loc[a_, "全規模"], "労働分配率_終点": ls.loc[b_, "全規模"],
        "始点の分配率を維持した場合の追加人件費_兆円": (ls.loc[a_, "全規模"] * va_all.loc[b_, "付加価値"] - va_all.loc[b_, "人件費"]) / MIL,
    }
pd.DataFrame(dist).T.to_csv(D / "value_added_distribution.csv", encoding="utf-8-sig")

pp = pd.DataFrame({
    "一人当たり付加価値": va_all["付加価値"] / va_all["人数"],
    "一人当たり人件費": va_all["人件費"] / va_all["人数"],
}) * 1e6 / 1e4  # 万円
pp["人数_万人"] = va_all["人数"] / 1e4
pp.index.name = "年度"
pp.round(2).to_csv(D / "per_person_va_labor_cost.csv", encoding="utf-8-sig")
before = ls.loc[1980:2024, "全規模"]
metrics["labor_share"] = {
    "全規模_2012": ls.loc[2012, "全規模"], "全規模_2025": ls.loc[2025, "全規模"],
    "全規模_1980から2024の最小": before.min(), "最小の年度": int(before.idxmin()),
    "全規模_1980から2024の平均": before.mean(), "全規模_2000から2019の平均": ls.loc[2000:2019, "全規模"].mean(),
    "10億円以上_2012": ls.loc[2012, "資本金10億円以上"], "10億円以上_2025": ls.loc[2025, "資本金10億円以上"],
    "10億円未満_2012": ls.loc[2012, "資本金10億円未満"], "10億円未満_2025": ls.loc[2025, "資本金10億円未満"],
    "付加価値に占める10億円以上のシェア_2012": va_big.loc[2012, "付加価値"] / va_all.loc[2012, "付加価値"],
    "付加価値に占める10億円以上のシェア_2025": va_big.loc[2025, "付加価値"] / va_all.loc[2025, "付加価値"],
    "分配": dist,
    "一人当たり付加価値_2012_万円": pp.loc[2012, "一人当たり付加価値"], "一人当たり付加価値_2025_万円": pp.loc[2025, "一人当たり付加価値"],
    "一人当たり人件費_2012_万円": pp.loc[2012, "一人当たり人件費"], "一人当たり人件費_2025_万円": pp.loc[2025, "一人当たり人件費"],
    "一人当たり付加価値_増加率": pp.loc[2025, "一人当たり付加価値"] / pp.loc[2012, "一人当たり付加価値"] - 1,
    "一人当たり人件費_増加率": pp.loc[2025, "一人当たり人件費"] / pp.loc[2012, "一人当たり人件費"] - 1,
    "人数_2012_万人": pp.loc[2012, "人数_万人"], "人数_2025_万人": pp.loc[2025, "人数_万人"],
}
# 構成比の変化の寄与（シェア変化を、規模内の変化と規模間の構成変化に分ける）
w0, w1 = metrics["labor_share"]["付加価値に占める10億円以上のシェア_2012"], metrics["labor_share"]["付加価値に占める10億円以上のシェア_2025"]
s_big0, s_big1 = ls.loc[2012, "資本金10億円以上"], ls.loc[2025, "資本金10億円以上"]
s_sm0, s_sm1 = ls.loc[2012, "資本金10億円未満"], ls.loc[2025, "資本金10億円未満"]
within = (w0 * (s_big1 - s_big0) + (1 - w0) * (s_sm1 - s_sm0))
mix = ((w1 - w0) * (s_big1 - s_sm1))
metrics["labor_share"]["全規模の変化_規模内の変化による_pt"] = within * 100
metrics["labor_share"]["全規模の変化_規模間の構成変化による_pt"] = mix * 100
metrics["labor_share"]["全規模の変化_合計_pt"] = (ls.loc[2025, "全規模"] - ls.loc[2012, "全規模"]) * 100


# ---- 8. 売上高を物価で割る（実質需要の目安） ----
defl = pd.read_csv(D / "deflators_fy.csv", index_col=0)
sales = h["売上高"]
rs = pd.DataFrame({"名目売上高": sales, **{k: defl[k] for k in defl.columns}}).loc[BASE:LAST].dropna()
rs["両指数の平均"] = rs[list(defl.columns)].mean(axis=1)
real = {
    "名目売上高": rs["名目売上高"],
    "実質売上高_企業物価で割る": rs["名目売上高"] / rs["国内企業物価指数_総平均"],
    "実質売上高_サービス価格で割る": rs["名目売上高"] / rs["企業向けサービス価格指数_総平均"],
    "実質売上高_両指数の平均で割る": rs["名目売上高"] / rs["両指数の平均"],
    "国内企業物価指数": rs["国内企業物価指数_総平均"],
    "企業向けサービス価格指数": rs["企業向けサービス価格指数_総平均"],
}
ri = pd.DataFrame(real)
ri = ri / ri.loc[BASE] * 100
ri.index.name = "年度"
ri.round(3).to_csv(D / "real_sales_index.csv", encoding="utf-8-sig")
metrics["real_sales"] = {
    "名目売上高_増加率": ri.loc[LAST, "名目売上高"] / 100 - 1,
    "国内企業物価指数_上昇率": ri.loc[LAST, "国内企業物価指数"] / 100 - 1,
    "企業向けサービス価格指数_上昇率": ri.loc[LAST, "企業向けサービス価格指数"] / 100 - 1,
    "実質売上高_企業物価で割る_増加率": ri.loc[LAST, "実質売上高_企業物価で割る"] / 100 - 1,
    "実質売上高_サービス価格で割る_増加率": ri.loc[LAST, "実質売上高_サービス価格で割る"] / 100 - 1,
    "実質売上高_両指数の平均で割る_増加率": ri.loc[LAST, "実質売上高_両指数の平均で割る"] / 100 - 1,
    "注意": "売上高は取引段階の重複（卸売など）と輸出売上を含む総額。企業物価は国内向けの財、サービス価格は企業向けで、法人企業統計の売上の物価を正確に表さない。実質需要の目安にとどまる。",
}

# ---- 9. 営業利益率の上昇の中身（売上原価率・販管費率） ----
cs = pd.read_csv(RAW / "houjin_table1_all_ex_fin_cost_structure_FY1980_2025.csv").set_index("年度")
assert (cs["売上高"] - cs["売上原価"] - cs["販売費及び一般管理費"] - cs["営業利益"]).abs().max() == 0
ratio = pd.DataFrame({
    "売上原価率": cs["売上原価"] / cs["売上高"],
    "販管費率": cs["販売費及び一般管理費"] / cs["売上高"],
    "営業利益率": cs["営業利益"] / cs["売上高"],
    "人件費率": va_all["人件費"] / cs["売上高"],
    "減価償却費率": va_all["減価償却費計"] / cs["売上高"],
}) * 100
ratio.index.name = "年度"
ratio.round(4).to_csv(D / "cost_ratios.csv", encoding="utf-8-sig")
dr = ratio.loc[LAST] - ratio.loc[BASE]
metrics["cost_structure"] = {
    "売上原価率_2012": ratio.loc[BASE, "売上原価率"], "売上原価率_2025": ratio.loc[LAST, "売上原価率"],
    "販管費率_2012": ratio.loc[BASE, "販管費率"], "販管費率_2025": ratio.loc[LAST, "販管費率"],
    "営業利益率_2012": ratio.loc[BASE, "営業利益率"], "営業利益率_2025": ratio.loc[LAST, "営業利益率"],
    "営業利益率の変化_pt": dr["営業利益率"], "売上原価率の変化_pt": dr["売上原価率"], "販管費率の変化_pt": dr["販管費率"],
    "人件費率の変化_pt": dr["人件費率"], "人件費率_2012": ratio.loc[BASE, "人件費率"], "人件費率_2025": ratio.loc[LAST, "人件費率"],
    "人件費以外の売上原価・販管費の率の変化_pt": (dr["売上原価率"] + dr["販管費率"]) - dr["人件費率"],
    "注意": "人件費は売上原価と販管費の両方に含まれる。売上原価率の低下の何割が人件費由来かは、この表からは分けられない",
}

def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if hasattr(o, "item"):
        return o.item()
    return o


(D / "metrics.json").write_text(json.dumps(clean(metrics), ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(clean({k: v for k, v in metrics.items() if k != "営業利益率_系列"}), ensure_ascii=False, indent=1))
