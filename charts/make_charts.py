"""記事の全図を作る。data/ のCSV（build_data.py, analyze.py の出力）だけを読む。

実行: python charts/make_charts.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
OUT = ROOT / "charts"
MIL = 1e6

BLUE, ORANGE, GRAY, DARK, TEAL, RED = "#2875b9", "#d56b2d", "#656565", "#222222", "#1f8a70", "#b34d79"
SRC_HOUJIN = "出所：財務省「法人企業統計調査」（金融業・保険業を除く全産業・全規模、年度）"


def choose_font():
    names = {f.name for f in font_manager.fontManager.ttflist}
    for name in ["Yu Gothic", "Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic"]:
        if name in names:
            plt.rcParams["font.family"] = name
            break
    else:
        import japanize_matplotlib  # noqa: F401
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 13, "text.color": "#222222"})


def frame(title, subtitle, note, source, ncols=1, figsize=(11, 7.0)):
    fig, axes = plt.subplots(1, ncols, figsize=figsize, dpi=190, squeeze=False)
    fig.patch.set_facecolor("white")
    for ax in axes[0]:
        for s in ["top", "right"]:
            ax.spines[s].set_visible(False)
        for s in ["bottom", "left"]:
            ax.spines[s].set_color("#aaaaaa")
        ax.grid(axis="y", color="#e2e2e2", lw=0.7, zorder=0)
        ax.set_axisbelow(True)
    fig.text(0.07, 0.96, title, ha="left", va="top", fontsize=20, weight="bold")
    fig.text(0.07, 0.902, subtitle, ha="left", va="top", fontsize=13.5, color="#555555")
    fig.text(0.07, 0.035, note + "\n" + source, ha="left", va="bottom", fontsize=13, color="#4a4a4a", linespacing=1.55)
    fig.subplots_adjust(left=0.10, right=0.965, top=0.80, bottom=0.27, wspace=0.18)
    return fig, (axes[0] if ncols > 1 else axes[0][0])


def save(fig, name):
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / name, facecolor="white")
    plt.close(fig)


def end_label(ax, x, y, text, color, dy=0, dx=8, size=14.5):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", color=color, fontsize=size, va="center")


def main():
    choose_font()
    m = pd.read_csv(D / "merged_fy_million_yen_and_oku_yen.csv", index_col=0)
    h = pd.read_csv(ROOT / "data/raw/houjin_table1_all_ex_fin_FY1980_2025.csv").set_index("年度")
    ke, op, noi, noe = (h[c] / MIL for c in ["経常利益", "営業利益", "営業外収益", "営業外費用"])
    ie = h["支払利息等"] / MIL

    # 図1 経常利益と営業利益
    fig, ax = frame("図1　経常利益は過去最高を更新している", "1980〜2025年度・兆円（名目）",
                    "注：全産業（金融業・保険業を除く）。経常利益＝営業利益＋営業外収益−営業外費用。\n名目値で、物価の影響は調整していない。", SRC_HOUJIN)
    ax.plot(ke.index, ke, color=DARK, lw=2.6)
    ax.plot(op.index, op, color=BLUE, lw=2.2, ls="--")
    ax.plot([2012], [ke[2012]], "o", color=DARK, ms=6)
    ax.annotate("2012年度\n48.5兆円", (2012, ke[2012]), xytext=(-8, 28), textcoords="offset points", ha="right", fontsize=13.5, arrowprops=dict(arrowstyle="-", color="#999999"))
    end_label(ax, 2025, ke[2025], f"経常利益\n{ke[2025]:.1f}兆円", DARK, dy=8)
    end_label(ax, 2025, op[2025], f"営業利益\n{op[2025]:.1f}兆円", BLUE, dy=-12)
    ax.set_xlim(1980, 2038)
    ax.set_xticks([1980, 1990, 2000, 2010, 2020, 2025])
    ax.set_ylabel("兆円")
    ax.set_ylim(0, 135)
    save(fig, "fig1_ordinary_profit.png")

    # 図2 ウォーターフォール
    dd = pd.read_csv(D / "decomposition.csv", index_col=0).loc["2012->2025"]
    a, b = dd["経常利益_始点_兆円"], dd["経常利益_終点_兆円"]
    d1, d2, d3 = dd["営業利益_兆円"], dd["営業外収益_兆円"], dd["営業外費用の増加_兆円"]
    fig, ax = frame("図2　最高益の増加分は、営業利益が約7割、営業外収益が約4割", "経常利益の増加分（2012年度→2025年度）の内訳・兆円",
                    "注：全産業（金融業・保険業を除く）、名目値。営業外費用の増加は差し引くので、\n割合は営業利益＋営業外収益−営業外費用＝100％になる。", SRC_HOUJIN + "より計算")
    xs = range(5)
    labels = ["2012年度\n経常利益", "営業利益の\n増加", "営業外収益の\n増加", "営業外費用の\n増加", "2025年度\n経常利益"]
    bottoms = [0, a, a + d1, a + d1 + d2 - d3, 0]
    heights = [a, d1, d2, d3, b]
    colors = [DARK, BLUE, ORANGE, GRAY, DARK]
    ax.bar(xs, heights, bottom=bottoms, color=colors, width=0.58, zorder=3)
    tops = [a, a + d1, a + d1 + d2, a + d1 + d2, b]
    texts = [f"{a:.1f}", f"+{d1:.1f}\n（{dd['営業利益_割合']*100:.0f}％）", f"+{d2:.1f}\n（{dd['営業外収益_割合']*100:.0f}％）",
             f"−{d3:.1f}\n（−{-dd['営業外費用_割合']*100:.0f}％）", f"{b:.1f}"]
    for x, t, y in zip(xs, texts, tops):
        ax.text(x, y + 2.5, t, ha="center", va="bottom", fontsize=15, weight="bold", color=DARK)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=13.5)
    ax.set_ylabel("兆円")
    ax.set_ylim(0, 150)
    save(fig, "fig2_waterfall.png")

    # 図3 営業外収益と国際収支の直接投資収益
    bp = m[["直接投資収益_受取", "直接投資_配当金配分済支店収益_受取", "直接投資_再投資収益_受取"]].dropna() / 1e4
    fig, ax = frame("図3　営業外収益は31兆円増、海外からの配当等は全部門で15兆円増", "営業外収益（法人企業統計）と直接投資収益（国際収支）・兆円",
                    "注：直接投資収益は全部門の受取で、金融機関も含むため、法人企業統計の対象より広い。\n再投資収益は内部留保の推計で、法人企業統計の営業外収益には現れない。\n2024・2025年度の再投資収益は暫定（点線）。外国証券からの配当・利子は含めていない。",
                    "出所：財務省「法人企業統計調査」、日本銀行「国際収支統計」（BPM6）")
    x0 = 1996
    ax.plot(noi.loc[x0:].index, noi.loc[x0:], color=ORANGE, lw=2.8)
    ax.plot(bp.loc[x0:].index, bp.loc[x0:, "直接投資収益_受取"], color=BLUE, lw=2.2)
    ax.plot(bp.loc[x0:].index, bp.loc[x0:, "直接投資_配当金配分済支店収益_受取"], color="#164e80", lw=2.0, ls="--")
    r = bp.loc[x0:, "直接投資_再投資収益_受取"]
    ax.plot(r.loc[:2023].index, r.loc[:2023], color=TEAL, lw=2.0, ls=":")
    ax.plot(r.loc[2023:].index, r.loc[2023:], color=TEAL, lw=1.4, ls=(0, (1, 3)), alpha=0.7)
    end_label(ax, 2025, noi[2025], f"営業外収益\n{noi[2025]:.1f}", ORANGE, dy=6, size=14)
    end_label(ax, 2025, bp.loc[2025, "直接投資収益_受取"], f"直接投資収益（受取）\n{bp.loc[2025,'直接投資収益_受取']:.1f}", BLUE, dy=2, size=14)
    end_label(ax, 2025, bp.loc[2025, "直接投資_配当金配分済支店収益_受取"], f"うち配当金など\n{bp.loc[2025,'直接投資_配当金配分済支店収益_受取']:.1f}", "#164e80", dy=10, size=14)
    end_label(ax, 2025, bp.loc[2025, "直接投資_再投資収益_受取"], f"うち再投資収益\n{bp.loc[2025,'直接投資_再投資収益_受取']:.1f}", TEAL, dy=-34, size=14)
    ax.set_xlim(1996, 2040)
    ax.set_xticks([1996, 2000, 2005, 2010, 2015, 2020, 2025])
    ax.set_ylabel("兆円")
    ax.set_ylim(0, 60)
    save(fig, "fig3_nonop_vs_bop.png")

    # 図4 円安の寄与
    cf = pd.read_csv(D / "fx_counterfactual.csv", index_col=0)
    fig, ax = frame("図4　為替を2012年度に固定すると、直接投資収益の円換算は14兆円小さい", "直接投資収益（受取）の円換算：実際と、2012年度の為替レートに固定した場合・兆円",
                    "注：直接投資収益の全額がドル建てと仮定した試算。再投資収益の分（約6兆円）は単体の営業外収益に現れない。\n営業利益に含まれる輸出採算への円安効果や、ドル以外の通貨の動きは含まない。\nドル円は年度平均（2012年度83円、2025年度151円）。",
                    "出所：日本銀行「国際収支統計」「時系列統計データ検索サイト」より計算")
    ax.fill_between(cf.index, cf["円レート固定_兆円"], cf["直接投資収益_受取_兆円"], color=ORANGE, alpha=0.22, zorder=2)
    ax.plot(cf.index, cf["直接投資収益_受取_兆円"], color=BLUE, lw=2.6)
    ax.plot(cf.index, cf["円レート固定_兆円"], color=GRAY, lw=2.2, ls="--")
    last = cf.index[-1]
    end_label(ax, last, cf.loc[last, "直接投資収益_受取_兆円"], f"実際\n{cf.loc[last,'直接投資収益_受取_兆円']:.1f}", BLUE, dy=4)
    end_label(ax, last, cf.loc[last, "円レート固定_兆円"], f"2012年度の\nレート固定\n{cf.loc[last,'円レート固定_兆円']:.1f}", GRAY, dy=-6)
    ax.text(2023.2, 22.0, f"為替の換算差\n約{cf.loc[last,'円安の寄与_兆円']:.0f}兆円", ha="center", va="center", color="#9a4a1c", fontsize=15, weight="bold", zorder=5)
    ax.set_xlim(2012, 2029)
    ax.set_xticks([2012, 2015, 2018, 2021, 2024, 2025])
    ax.set_ylabel("兆円")
    ax.set_ylim(0, 38)
    save(fig, "fig4_fx_counterfactual.png")

    # 図5 SNAとの突き合わせ
    c = pd.read_csv(D / "sna_vs_houjin.csv", index_col=0)
    fig, axes = frame("図5　SNAの営業余剰（純）は横ばい、法人企業統計の営業利益は2.6倍", "非金融法人企業の営業利益・営業余剰（1994〜2024年・兆円）",
                      "注：法人企業統計は年度、SNAは暦年で、年度tを暦年tに対応させた。範囲も異なる\n（法人企業統計は金融業・保険業を除く、SNAは非金融法人企業）。\nSNAの固定資本減耗は時価、法人企業統計の減価償却費は帳簿価額。",
                      "出所：財務省「法人企業統計調査」、内閣府「国民経済計算」2024年度年次推計（2020年基準）", ncols=2)
    ax1, ax2 = axes
    for ax in axes:
        ax.set_xlim(1994, 2024)
        ax.set_xticks([1994, 2004, 2014, 2024])
        ax.set_ylim(0, 185)
    ax1.set_ylabel("兆円")
    ax1.set_title("総（減価償却・固定資本減耗の控除前）", fontsize=14, loc="left", color="#444444")
    ax1.plot(c.index, c["法人企業統計_営業利益＋減価償却費_兆円"], color=BLUE, lw=2.4)
    ax1.plot(c.index, c["SNA_営業余剰_総_兆円"], color=DARK, lw=2.4, ls="--")
    ax1.text(1995, 156, "SNA 営業余剰（総）", color=DARK, fontsize=13.5)
    ax1.text(1995, 40, "法人企業統計\n営業利益＋減価償却費", color=BLUE, fontsize=13.5, va="center")
    ax2.set_title("純（減価償却・固定資本減耗の控除後）", fontsize=14, loc="left", color="#444444")
    ax2.plot(c.index, c["法人企業統計_営業利益_兆円"], color=BLUE, lw=2.4)
    ax2.plot(c.index, c["SNA_営業余剰_純_兆円"], color=DARK, lw=2.4, ls="--")
    ax2.text(1995, 90, "SNA 営業余剰（純）", color=DARK, fontsize=13.5)
    ax2.text(1995, 12, "法人企業統計 営業利益", color=BLUE, fontsize=13.5, va="center")
    save(fig, "fig5_sna_vs_houjin.png")

    # 図6 支払利息等
    fig, ax = frame("図6　支払利息は営業利益の6割から1割へ減り、足元でやや戻した", "営業利益と支払利息等（1980〜2025年度・兆円）",
                    "注：全産業（金融業・保険業を除く）。支払利息等は営業外費用の主な内訳（割引料を含む）。\n営業外費用のうち支払利息等以外の内訳は、この表では分からない。", SRC_HOUJIN)
    ax.plot(op.index, op, color=BLUE, lw=2.4)
    ax.plot(ie.index, ie, color=GRAY, lw=2.4)
    for y in (1995, 2012, 2025):
        ratio = ie[y] / op[y] * 100
        ax.plot([y], [ie[y]], "o", color=GRAY, ms=5)
        ax.annotate(f"{y}年度\n営業利益の{ratio:.0f}％", (y, ie[y]), xytext=(0, -12), textcoords="offset points", ha="center", va="top", fontsize=13, color="#444444")
    end_label(ax, 2025, op[2025], f"営業利益\n{op[2025]:.1f}", BLUE, dy=4)
    end_label(ax, 2025, ie[2025], f"支払利息等\n{ie[2025]:.1f}", GRAY, dy=16)
    ax.set_xlim(1980, 2036)
    ax.set_xticks([1980, 1990, 2000, 2010, 2020, 2025])
    ax.set_ylabel("兆円")
    ax.set_ylim(-22, 105)
    save(fig, "fig6_interest.png")
    # 図7 労働分配率
    ls = pd.read_csv(D / "labor_share_by_size.csv", index_col=0) * 100
    fig, ax = frame("図7　労働分配率は63％まで下がり、1980年度以降で最低", "労働分配率＝人件費÷付加価値（1980〜2025年度・％）",
                    "注：人件費は役員・従業員の給与・賞与と福利厚生費。付加価値＝人件費＋支払利息等＋賃借料\n＋租税公課＋営業純益。金融業・保険業を除く全産業。資本金10億円未満は全規模から10億円以上を引いて算出。\n役員賞与はFY2007から人件費に含まれる（表の区分の変更で、影響は付加価値の0.2〜0.4％程度）。", SRC_HOUJIN + "より計算")
    ax.plot(ls.index, ls["資本金10億円未満"], color=GRAY, lw=2.0, ls="-.")
    ax.plot(ls.index, ls["資本金10億円以上"], color=ORANGE, lw=2.0, ls="--")
    ax.plot(ls.index, ls["全規模"], color=DARK, lw=2.8)
    ax.plot([2012], [ls.loc[2012, "全規模"]], "o", color=DARK, ms=6)
    ax.annotate(f"2012年度 {ls.loc[2012,'全規模']:.1f}％", (2012, ls.loc[2012, "全規模"]), xytext=(2014.5, 63.5), textcoords="data", ha="left", va="center", fontsize=13.5,
                arrowprops=dict(arrowstyle="-", color="#999999"))
    end_label(ax, 2025, ls.loc[2025, "資本金10億円未満"], f"資本金10億円未満\n{ls.loc[2025,'資本金10億円未満']:.1f}％", GRAY, dy=6, size=13.5)
    end_label(ax, 2025, ls.loc[2025, "全規模"], f"全規模\n{ls.loc[2025,'全規模']:.1f}％", DARK, dy=-2, size=14.5)
    end_label(ax, 2025, ls.loc[2025, "資本金10億円以上"], f"資本金10億円以上\n{ls.loc[2025,'資本金10億円以上']:.1f}％", ORANGE, dy=0, size=13.5)
    ax.set_xlim(1980, 2043)
    ax.set_xticks([1980, 1990, 2000, 2010, 2020, 2025])
    ax.set_ylabel("％")
    ax.set_ylim(40, 85)
    save(fig, "fig7_labor_share.png")

    # 図8 付加価値の増加分の行き先
    vd = pd.read_csv(D / "value_added_distribution.csv", index_col=0).loc["2012->2025"]
    items = [("営業純益", "営業純益_兆円", "営業純益_割合", ORANGE), ("人件費", "人件費_兆円", "人件費_割合", BLUE),
             ("動産・不動産\n賃借料", "動産不動産賃借料_兆円", "動産不動産賃借料_割合", GRAY), ("租税公課", "租税公課_兆円", "租税公課_割合", GRAY),
             ("支払利息等", "支払利息等_兆円", "支払利息等_割合", GRAY)]
    fig, ax = frame("図8　付加価値の増加分の約5割は営業純益、人件費は約4割", f"付加価値の増加分（2012年度→2025年度、{vd['付加価値_増分_兆円']:.1f}兆円）の行き先・兆円",
                    "注：付加価値＝人件費＋支払利息等＋賃借料＋租税公課＋営業純益。営業純益＝営業利益−支払利息等。\n金融業・保険業を除く全産業、名目値。割合の合計は100％。", SRC_HOUJIN + "より計算")
    for i, (lab, kv, kr, col) in enumerate(items):
        ax.bar(i, vd[kv], color=col, width=0.58, zorder=3)
        ax.text(i, vd[kv] + 1.0, f"+{vd[kv]:.1f}\n（{vd[kr]*100:.0f}％）", ha="center", va="bottom", fontsize=15, weight="bold", color=DARK)
    ax.set_xticks(range(len(items)))
    ax.set_xticklabels([x[0] for x in items], fontsize=13.5)
    ax.set_ylabel("兆円")
    ax.set_ylim(0, 62)
    save(fig, "fig8_value_added_distribution.png")

    # 図9 一人当たり付加価値と人件費
    pp = pd.read_csv(D / "per_person_va_labor_cost.csv", index_col=0).loc[2012:]
    idx = pp[["一人当たり付加価値", "一人当たり人件費"]] / pp[["一人当たり付加価値", "一人当たり人件費"]].loc[2012] * 100
    fig, ax = frame("図9　一人当たり付加価値は29％増、一人当たり人件費は12％増", "従業員・役員一人当たり（2012年度＝100）",
                    f"注：名目値で、物価の影響は調整していない。人数は期中平均の従業員数と役員数の合計。2012年度→2025年度で、\n一人当たり付加価値は{pp.loc[2012,'一人当たり付加価値']:.0f}万円→{pp.loc[2025,'一人当たり付加価値']:.0f}万円、"
                    f"一人当たり人件費は{pp.loc[2012,'一人当たり人件費']:.0f}万円→{pp.loc[2025,'一人当たり人件費']:.0f}万円。金融業・保険業を除く全産業。", SRC_HOUJIN + "より計算")
    ax.axhline(100, color="#999999", ls=":", lw=0.9)
    ax.plot(idx.index, idx["一人当たり付加価値"], color=ORANGE, lw=2.6)
    ax.plot(idx.index, idx["一人当たり人件費"], color=BLUE, lw=2.6, ls="--")
    end_label(ax, 2025, idx.iloc[-1]["一人当たり付加価値"], f"一人当たり付加価値\n{idx.iloc[-1]['一人当たり付加価値']:.1f}", ORANGE, dy=2, size=14)
    end_label(ax, 2025, idx.iloc[-1]["一人当たり人件費"], f"一人当たり人件費\n{idx.iloc[-1]['一人当たり人件費']:.1f}", BLUE, dy=-2, size=14)
    ax.set_xlim(2012, 2030)
    ax.set_xticks([2012, 2015, 2018, 2021, 2024, 2025])
    ax.set_ylabel("2012年度＝100")
    ax.set_ylim(90, 135)
    save(fig, "fig9_per_person.png")
    # 図10 名目売上高と、物価で割った売上高
    ri = pd.read_csv(D / "real_sales_index.csv", index_col=0)
    fig, ax = frame("図10　売上高は名目で25％増だが、物価で割ると横ばい", "売上高と物価の推移（2012年度＝100）",
                    "注：売上高は取引段階の重複や輸出売上を含む総額。実質売上高は、国内企業物価指数（財）と企業向けサービス\n価格指数の平均で割った目安で、法人企業統計の売上の物価を正確に表すものではない。金融業・保険業を除く全産業。",
                    "出所：財務省「法人企業統計調査」、日本銀行「企業物価指数」「企業向けサービス価格指数」より計算")
    ax.axhline(100, color="#999999", ls=":", lw=0.9)
    ax.plot(ri.index, ri["名目売上高"], color=DARK, lw=2.8)
    ax.plot(ri.index, ri["実質売上高_両指数の平均で割る"], color=ORANGE, lw=2.8)
    ax.plot(ri.index, ri["国内企業物価指数"], color=GRAY, lw=1.8, ls="--")
    ax.plot(ri.index, ri["企業向けサービス価格指数"], color=GRAY, lw=1.8, ls=":")
    last = ri.index[-1]
    end_label(ax, last, ri.loc[last, "国内企業物価指数"], f"企業物価（財） {ri.loc[last,'国内企業物価指数']:.1f}", GRAY, dy=9, size=13.5)
    end_label(ax, last, ri.loc[last, "名目売上高"], f"名目売上高 {ri.loc[last,'名目売上高']:.1f}", DARK, dy=0, size=14.5)
    end_label(ax, last, ri.loc[last, "企業向けサービス価格指数"], f"サービス価格 {ri.loc[last,'企業向けサービス価格指数']:.1f}", GRAY, dy=-10, size=13.5)
    end_label(ax, last, ri.loc[last, "実質売上高_両指数の平均で割る"], f"実質売上高（目安） {ri.loc[last,'実質売上高_両指数の平均で割る']:.1f}", ORANGE, dy=0, size=14.5)
    ax.set_xlim(2012, 2033)
    ax.set_xticks([2012, 2015, 2018, 2021, 2024, 2025])
    ax.set_ylabel("2012年度＝100")
    ax.set_ylim(90, 138)
    save(fig, "fig10_real_sales.png")
    # 図11 営業利益率の上昇の中身
    cr = pd.read_csv(D / "cost_ratios.csv", index_col=0)
    r0, r1 = cr.loc[2012], cr.loc[2025]
    lab = r0["人件費率"] - r1["人件費率"]
    oth = (r0["売上原価率"] + r0["販管費率"] - r0["人件費率"]) - (r1["売上原価率"] + r1["販管費率"] - r1["人件費率"])
    fig, ax = frame("図11　利益率の上昇2.5ポイントのうち、人件費の寄与は約4分の1", "営業利益率の変化（2012年度→2025年度・売上高に対する％）",
                    "注：営業利益率＝営業利益÷売上高。人件費は売上原価と販管費の両方に含まれるため、費用全体の率を\n人件費の率と、それ以外（仕入・材料・経費など）の率に分けた。金融業・保険業を除く全産業。",
                    SRC_HOUJIN + "より計算")
    xs = range(4)
    heights = [r0["営業利益率"], lab, oth, r1["営業利益率"]]
    bottoms = [0, r0["営業利益率"], r0["営業利益率"] + lab, 0]
    colors = [DARK, BLUE, ORANGE, DARK]
    ax.bar(xs, heights, bottom=bottoms, color=colors, width=0.58, zorder=3)
    tops = [heights[0], bottoms[1] + lab, bottoms[2] + oth, heights[3]]
    texts = [f"{r0['営業利益率']:.1f}％", f"+{lab:.2f}\n（{lab/(lab+oth)*100:.0f}％）", f"+{oth:.2f}\n（{oth/(lab+oth)*100:.0f}％）", f"{r1['営業利益率']:.1f}％"]
    for x, t_, y in zip(xs, texts, tops):
        ax.text(x, y + 0.12, t_, ha="center", va="bottom", fontsize=15, weight="bold", color=DARK)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(["2012年度\n営業利益率", "人件費率の\n低下", "人件費以外の\n費用率の低下", "2025年度\n営業利益率"], fontsize=13.5)
    ax.set_ylabel("％（ポイント）")
    ax.set_ylim(0, 6.9)
    save(fig, "fig11_margin_sources.png")
    print("saved:", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
