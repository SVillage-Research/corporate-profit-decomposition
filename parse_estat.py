"""e-Statの法人企業統計（時系列表1）からダウンロードしたファイル3つを読み、分析用の5つのCSVを data/raw/ に作る。

入力（data/estat/ に置く。ファイル名は自由。CSVでもExcel（.xlsx）でもよい）:
  業種＝全産業（除く金融保険業）、規模＝全規模
  業種＝純粋持株会社、規模＝全規模
  業種＝全産業（除く金融保険業）、規模＝資本金10億円以上
どの表かは、ファイルの中の「業種」「規模」の値から自動で判定します。

出力（data/raw/）:
  houjin_table1_all_ex_fin_FY1980_2025.csv
  houjin_table1_pure_holding_FY2009_2025.csv
  houjin_table1_all_ex_fin_value_added_FY1980_2025.csv
  houjin_table1_capital_10oku_plus_value_added_FY1980_2025.csv
  houjin_table1_all_ex_fin_cost_structure_FY1980_2025.csv

読める形：e-Statの「ダウンロード」の次の形式
  (1) CSV（項目・業種・規模・年度・値が縦に並ぶ形）
  (2) Excel（上に表の説明があり、行が年度・列が項目の形）
  のほか、行が年度・列が項目のCSV、行が項目・列が年度のCSVも読めます。
列名の「(当期末)」や「【百万円】」などの違いは吸収します。必要な項目が見つからなければ、エラーで止まります。

実行: python parse_estat.py
"""
import csv
import io
import re
import sys
import warnings
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ESTAT = HERE / "data" / "estat"
RAW = HERE / "data" / "raw"

# 判定できない形式（行が年度の表など）のときだけ使う、決まったファイル名
INPUTS = {
    "all": "estat_all_ex_fin_all_size.csv",
    "holding": "estat_pure_holding_all_size.csv",
    "large": "estat_all_ex_fin_10oku_plus.csv",
}
DESC = {
    "all": "業種＝全産業（除く金融保険業）、規模＝全規模",
    "holding": "業種＝純粋持株会社、規模＝全規模",
    "large": "業種＝全産業（除く金融保険業）、規模＝10億円以上",
}
SELECT = {
    ("全産業（除く金融保険業）", "全規模"): "all",
    ("純粋持株会社", "全規模"): "holding",
    ("全産業（除く金融保険業）", "10億円以上"): "large",
}

# 出力の列名 ← e-Statの項目名（正規化後）
ITEM = {
    "母集団_社": "母集団",
    "資産合計": "資産合計",
    "売上高": "売上高",
    "売上原価": "売上原価",
    "販売費及び一般管理費": "販売費及び一般管理費",
    "営業利益": "営業利益",
    "営業外収益": "営業外収益",
    "営業外費用": "営業外費用",
    "経常利益": "経常利益",
    "特別利益": "特別利益",
    "特別損失": "特別損失",
    "当期純利益": "当期純利益",
    "配当金計": "配当金計",
    "社内留保": "社内留保",
    "減価償却費計": "減価償却費計",
    "役員給与": "役員給与",
    "役員賞与": "役員賞与",
    "従業員給与": "従業員給与",
    "従業員賞与": "従業員賞与",
    "福利厚生費": "福利厚生費",
    "支払利息等": "支払利息等",
    "動産不動産賃借料": "動産・不動産賃借料",
    "租税公課": "租税公課",
    "期中平均役員数_人": "期中平均役員数",
    "期中平均従業員数_人": "期中平均従業員数",
    "付加価値": "付加価値",
    "営業純益": "営業純益",
}

OUTPUTS = {
    "houjin_table1_all_ex_fin_FY1980_2025.csv": ("all", 1980, [
        "母集団_社", "資産合計", "売上高", "営業利益", "営業外収益", "営業外費用", "経常利益", "特別利益", "特別損失",
        "当期純利益", "配当金計", "社内留保", "減価償却費計", "従業員給与", "従業員賞与", "福利厚生費", "支払利息等",
        "期中平均従業員数_人", "付加価値"]),
    "houjin_table1_pure_holding_FY2009_2025.csv": ("holding", 2009, [
        "母集団_社", "資産合計", "売上高", "営業利益", "営業外収益", "営業外費用", "経常利益", "配当金計", "支払利息等",
        "期中平均従業員数_人"]),
    "houjin_table1_all_ex_fin_value_added_FY1980_2025.csv": ("all", 1980, [
        "売上高", "営業利益", "減価償却費計", "役員給与", "役員賞与", "従業員給与", "従業員賞与", "福利厚生費", "支払利息等",
        "動産不動産賃借料", "租税公課", "期中平均役員数_人", "期中平均従業員数_人", "付加価値", "営業純益"]),
    "houjin_table1_capital_10oku_plus_value_added_FY1980_2025.csv": ("large", 1980, [
        "母集団_社", "売上高", "営業利益", "減価償却費計", "役員給与", "役員賞与", "従業員給与", "従業員賞与", "福利厚生費",
        "支払利息等", "動産不動産賃借料", "租税公課", "期中平均役員数_人", "期中平均従業員数_人", "付加価値", "営業純益"]),
    "houjin_table1_all_ex_fin_cost_structure_FY1980_2025.csv": ("all", 1980, [
        "売上高", "売上原価", "販売費及び一般管理費", "営業利益"]),
}


def normalize(label):
    """項目名から、単位・（当期末）・空白・脚注記号を取り除く。"""
    s = str(label)
    s = re.sub(r"[\s　]+", "", s)
    s = re.sub(r"【[^】]*】", "", s)
    s = re.sub(r"[（(]当期末[）)]", "", s)
    s = s.replace("※", "")
    return s


def to_number(x):
    s = str(x).strip().replace(",", "").replace("，", "")
    if s in ("", "***", "*", "-", "－", "…", "x", "X", "nan", "None"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def read_rows(path):
    """CSV・Excelを、文字列の行のリストにして返す。"""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(path, data_only=True)  # read_only は、e-Statのxlsxの範囲情報が不完全で、行を取りこぼすので使わない
        ws = wb[wb.sheetnames[0]]
        rows = []
        for r in ws.iter_rows(values_only=True):
            rows.append(["" if v is None else (str(int(v)) if isinstance(v, float) and v == int(v) else str(v)) for v in r])
        return rows
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp932"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"{path}: 文字コードを判定できません")
    return [r for r in csv.reader(io.StringIO(text))]


YEAR = re.compile(r"^\s*(\d{4})\s*年?度?\s*$")
YEAR_STRICT = re.compile(r"^\s*(\d{4})\s*年度\s*$")


def read_estat_table(path):
    """行＝年度、列＝正規化した項目名の表を返す。"""
    rows = read_rows(path)
    # (1) e-StatのCSV（縦持ち）：cat01_code, 調査項目, cat02_code, 業種, cat03_code, 規模, time_code, 年度, unit, value
    for i, r in enumerate(rows):
        if "value" in r and any(str(c).startswith("調査項目") for c in r):
            col_item = next(j for j, c in enumerate(r) if str(c).startswith("調査項目"))
            col_time = next(j for j, c in enumerate(r) if re.sub(r"[\s　]+", "", str(c)) in ("年期", "年度", "時間軸"))
            col_val = r.index("value")
            data = {}
            for rr in rows[i + 1:]:
                if len(rr) <= max(col_item, col_time, col_val):
                    continue
                m = YEAR.match(rr[col_time])
                if not m:
                    continue
                name = normalize(rr[col_item])
                if not name:
                    continue
                data.setdefault(int(m.group(1)), {}).setdefault(name, to_number(rr[col_val]))  # 同名の項目は最初のものを使う
            df = pd.DataFrame.from_dict(data, orient="index").sort_index()
            df.index.name = "年度"
            return df
    # (2) Excel・行が年度のCSV：項目名の並ぶ行があり、データ行の先頭付近に「2009年度」のような年度がある
    for i, r in enumerate(rows):
        names = [normalize(c) for c in r]
        labels = [n for n in names if n and not re.fullmatch(r"[0-9,.\-]+", n)]
        if "売上高" in names and len(labels) >= 5:
            data = {}
            for rr in rows[i + 1:]:
                year = None
                for c in rr[:4]:
                    m = YEAR_STRICT.match(c)
                    if m:
                        year = int(m.group(1))
                        break
                if year is None and rr and YEAR.match(rr[0]):
                    year = int(YEAR.match(rr[0]).group(1))
                if year is None:
                    continue
                data[year] = {}
                for n, v in zip(names, rr):
                    if n and n not in data[year] and not YEAR.match(str(v)):
                        data[year][n] = to_number(v)
            df = pd.DataFrame.from_dict(data, orient="index").sort_index()
            df.index.name = "年度"
            return df
    # (3) 行が項目・列が年度のCSV
    for i, r in enumerate(rows):
        years = [(j, YEAR.match(c)) for j, c in enumerate(r)]
        years = [(j, int(m.group(1))) for j, m in years if m]
        if len(years) >= 10:
            data = {}
            for rr in rows[i + 1:]:
                if not rr or not normalize(rr[0]):
                    continue
                name = normalize(rr[0])
                data[name] = {y: to_number(rr[j]) for j, y in years if j < len(rr)}
            df = pd.DataFrame(data).sort_index()
            df.index.name = "年度"
            return df
    raise ValueError(f"{path}: 年度と項目（売上高・経常利益など）の表を見つけられませんでした")


def classify(path):
    """ファイルの中の「業種」「規模」の値から、どの表かを判定する（ファイル名は問わない）。判定できなければ None。"""
    try:
        rows = read_rows(path)
    except Exception:  # noqa: BLE001
        return None
    # Excel：先頭付近に「業種 (…)：、コード、名前」「規模 (…)：、コード、名前」の行がある
    industry = size = None
    for r in rows[:15]:
        if r and str(r[0]).startswith("業種"):
            vals = [c for c in r[1:] if str(c).strip()]
            industry = normalize(vals[-1]) if vals else None
        if r and str(r[0]).startswith("規模"):
            vals = [c for c in r[1:] if str(c).strip()]
            size = normalize(vals[-1]) if vals else None
    if industry and size:
        return SELECT.get((industry, size))
    # CSV（縦持ち）：「業種」「規模」の列の値がそれぞれ1種類
    for i, r in enumerate(rows):
        if "value" in r and any(str(c).startswith("調査項目") for c in r):
            ci = next((j for j, c in enumerate(r) if str(c).startswith("業種")), None)
            cs = next((j for j, c in enumerate(r) if str(c).startswith("規模")), None)
            if ci is None or cs is None:
                return None
            body = [x for x in rows[i + 1:i + 5000] if len(x) > max(ci, cs)]
            inds = {normalize(x[ci]) for x in body}
            sizes = {normalize(x[cs]) for x in body}
            if len(inds) == 1 and len(sizes) == 1:
                return SELECT.get((next(iter(inds)), next(iter(sizes))))
            return None
    return None


def pick(df, col):
    name = ITEM[col]
    if name not in df.columns:
        raise KeyError(f"項目「{name}」が見つかりません。e-Statの表で、全項目・全年度を選んでダウンロードしたか確認してください。")
    return df[name]


def fmt(v):
    return "" if pd.isna(v) else str(int(round(v)))


def main():
    found = {}
    for f in sorted(list(ESTAT.glob("*.csv")) + list(ESTAT.glob("*.xlsx"))):
        if f.name.startswith("~$"):
            continue
        k = classify(f)
        if k:
            found[k] = f
    for key, fname in INPUTS.items():  # 決まった名前のファイルがあれば、それを優先
        if (ESTAT / fname).exists():
            found[key] = ESTAT / fname
    missing = [k for k in INPUTS if k not in found]
    if missing:
        sys.exit("e-Statのファイルが足りません。data/estat/ に、次の表のファイルを置いてください（ファイル名は自由）:\n"
                 + "\n".join(f"  - {DESC[k]}" for k in missing))
    tables = {}
    for key, path in found.items():
        tables[key] = read_estat_table(path)
        print(f"OK  {path.name}（{DESC[key]}）: {tables[key].index.min()}〜{tables[key].index.max()}年度、{tables[key].shape[1]}項目")
    RAW.mkdir(parents=True, exist_ok=True)
    for out, (key, first, cols) in OUTPUTS.items():
        df = tables[key]
        df = df[df.index >= first]
        lines = ["年度," + ",".join(cols)]
        for y, row in df.iterrows():
            vals = [fmt(pick(df, c)[y]) for c in cols]
            lines.append(f"{y}," + ",".join(vals))
        (RAW / out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  → data/raw/{out}（{len(df)}年度）")


if __name__ == "__main__":
    main()
