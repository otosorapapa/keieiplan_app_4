"""Input hub for sales, costs, investments, borrowings and tax policy."""
from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

from formatting import UNIT_FACTORS, format_amount_with_unit, format_ratio
from models import (
    DEFAULT_CAPEX_PLAN,
    DEFAULT_COST_PLAN,
    DEFAULT_LOAN_SCHEDULE,
    DEFAULT_SALES_PLAN,
    DEFAULT_TAX_POLICY,
    MONTH_SEQUENCE,
)
from state import ensure_session_defaults
from theme import inject_theme
from validators import ValidationIssue, validate_bundle

st.set_page_config(
    page_title="経営計画スタジオ｜Inputs",
    page_icon="🧾",
    layout="wide",
)

inject_theme()
ensure_session_defaults()

finance_raw: Dict[str, Dict] = st.session_state.get("finance_raw", {})
if not finance_raw:
    finance_raw = {
        "sales": DEFAULT_SALES_PLAN.model_dump(),
        "costs": DEFAULT_COST_PLAN.model_dump(),
        "capex": DEFAULT_CAPEX_PLAN.model_dump(),
        "loans": DEFAULT_LOAN_SCHEDULE.model_dump(),
        "tax": DEFAULT_TAX_POLICY.model_dump(),
    }
    st.session_state["finance_raw"] = finance_raw

validation_errors: List[ValidationIssue] = st.session_state.get("finance_validation_errors", [])


MONTH_COLUMNS = [f"月{m:02d}" for m in MONTH_SEQUENCE]
SALES_TEMPLATE_STATE_KEY = "sales_template_df"
SALES_CHANNEL_COUNTER_KEY = "sales_channel_counter"
SALES_PRODUCT_COUNTER_KEY = "sales_product_counter"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

INPUT_WIZARD_STEP_KEY = "input_wizard_step"
BUSINESS_CONTEXT_KEY = "business_context"

WIZARD_STEPS = [
    {
        "id": "context",
        "title": "ビジネスモデル整理",
        "description": "3C分析とビジネスモデルキャンバスの主要項目を言語化します。",
    },
    {
        "id": "sales",
        "title": "売上計画",
        "description": "チャネル×商品×月で売上を想定し、季節性や販促を織り込みます。",
    },
    {
        "id": "costs",
        "title": "原価・経費",
        "description": "粗利益率を意識しながら変動費・固定費・営業外項目を整理します。",
    },
    {
        "id": "invest",
        "title": "投資・借入",
        "description": "成長投資と資金調達のスケジュールを設定します。",
    },
    {
        "id": "tax",
        "title": "税制・保存",
        "description": "税率と最終チェックを行い、入力内容を保存します。",
    },
]

BUSINESS_CONTEXT_TEMPLATE = {
    "three_c_customer": "",
    "three_c_company": "",
    "three_c_competitor": "",
    "bmc_customer_segments": "",
    "bmc_value_proposition": "",
    "bmc_channels": "",
    "qualitative_memo": "",
}

BUSINESS_CONTEXT_PLACEHOLDER = {
    "three_c_customer": "主要顧客やターゲット市場の概要",
    "three_c_company": "自社の強み・差別化要素",
    "three_c_competitor": "競合の特徴と比較ポイント",
    "bmc_customer_segments": "顧客セグメントの詳細像 (例：30代共働き世帯、法人経理部門など)",
    "bmc_value_proposition": "提供価値・顧客の課題解決方法 (例：在庫管理を自動化し月30時間削減)",
    "bmc_channels": "顧客に価値を届けるチャネル (例：ECサイト、代理店、直販営業)",
    "qualitative_memo": "事業計画書に記載したい補足・KGI/KPIの背景",
}

VARIABLE_RATIO_FIELDS = [
    (
        "COGS_MAT",
        "材料費 原価率",
        "材料費＝製品・サービス提供に使う原材料コスト。粗利益率＝(売上−売上原価)÷売上。製造業では30%を超えると優良とされます。",
    ),
    (
        "COGS_LBR",
        "外部労務費 原価率",
        "外部労務費＝外部人材への支払い。繁忙期の稼働計画を踏まえて設定しましょう。",
    ),
    (
        "COGS_OUT_SRC",
        "外注費(専属) 原価率",
        "専属パートナーに支払うコスト。受注量に応じた歩合を想定します。",
    ),
    (
        "COGS_OUT_CON",
        "外注費(委託) 原価率",
        "スポットで委託するコスト。最低発注量やキャンセル料も考慮してください。",
    ),
    (
        "COGS_OTH",
        "その他原価率",
        "その他の仕入や物流費など。粗利益率が目標レンジに収まるか確認しましょう。",
    ),
]

FIXED_COST_FIELDS = [
    (
        "OPEX_H",
        "人件費",
        "正社員・パート・役員報酬などを合算。採用・昇給計画をメモに残すと振り返りやすくなります。",
    ),
    (
        "OPEX_K",
        "経費",
        "家賃・広告宣伝・通信費などの販管費。固定化している支出を中心に入力します。",
    ),
    (
        "OPEX_DEP",
        "減価償却費",
        "過去投資の償却費。税務上の耐用年数を確認しましょう。",
    ),
]

NOI_FIELDS = [
    (
        "NOI_MISC",
        "雑収入",
        "本業以外の収益。補助金やポイント還元など小さな収益源もここに集約します。",
    ),
    (
        "NOI_GRANT",
        "補助金",
        "行政や財団からの補助金収入。採択時期と入金月を想定しておきましょう。",
    ),
    (
        "NOI_OTH",
        "その他営業外収益",
        "受取利息や資産売却益など。単発か継続かをメモしておくと精度が上がります。",
    ),
]

NOE_FIELDS = [
    (
        "NOE_INT",
        "支払利息",
        "借入に伴う金利コスト。借入スケジュールと連動しているか確認しましょう。",
    ),
    (
        "NOE_OTH",
        "その他費用",
        "雑損失や為替差損など一時的な費用。発生条件をメモすると再計算に便利です。",
    ),
]

TAX_FIELD_META = {
    "corporate": "法人税率＝課税所得にかかる税率。中小企業は約30%が目安です。",
    "consumption": "消費税率＝売上に上乗せする税率。免税事業者の場合は0%に設定します。",
    "dividend": "配当性向＝税引後利益に対する配当割合。成長投資を優先する場合は低めに設定。",
}


def _ensure_sales_template_state(base_df: pd.DataFrame) -> None:
    if SALES_TEMPLATE_STATE_KEY not in st.session_state:
        st.session_state[SALES_TEMPLATE_STATE_KEY] = base_df.copy()
        unique_channels = base_df["チャネル"].dropna().unique()
        unique_products = base_df["商品"].dropna().unique()
        st.session_state[SALES_CHANNEL_COUNTER_KEY] = len(unique_channels) + 1
        st.session_state[SALES_PRODUCT_COUNTER_KEY] = len(unique_products) + 1


def _standardize_sales_df(df: pd.DataFrame) -> pd.DataFrame:
    base = df.copy()
    base.columns = [str(col).strip() for col in base.columns]
    if "チャネル" not in base.columns or "商品" not in base.columns:
        raise ValueError("テンプレートには『チャネル』『商品』列が必要です。")
    for month_col in MONTH_COLUMNS:
        if month_col not in base.columns:
            base[month_col] = 0.0
    ordered = ["チャネル", "商品", *MONTH_COLUMNS]
    base = base[ordered]
    base["チャネル"] = base["チャネル"].fillna("").astype(str)
    base["商品"] = base["商品"].fillna("").astype(str)
    for month_col in MONTH_COLUMNS:
        base[month_col] = (
            pd.to_numeric(base[month_col], errors="coerce").fillna(0.0).astype(float)
        )
    return base


def _sales_template_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def _sales_template_to_excel(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SalesTemplate", index=False)
    buffer.seek(0)
    return buffer.read()


def _load_sales_template_from_upload(upload: io.BytesIO | None) -> pd.DataFrame | None:
    if upload is None:
        return None
    file_size = getattr(upload, "size", None)
    if file_size is not None and file_size > MAX_UPLOAD_BYTES:
        st.error("アップロードできるファイルサイズは5MBまでです。")
        return None
    mime_type = getattr(upload, "type", "") or ""
    file_name = getattr(upload, "name", "")
    extension = Path(str(file_name)).suffix.lower()
    if mime_type and mime_type not in ALLOWED_MIME_TYPES:
        st.error("CSVまたはExcel形式のファイルをアップロードしてください。")
        return None
    if extension not in ALLOWED_EXTENSIONS:
        st.error("拡張子が .csv または .xlsx のファイルのみ受け付けます。")
        return None
    try:
        if extension == ".csv":
            df = pd.read_csv(upload)
        else:
            df = pd.read_excel(upload)
    except Exception:
        st.error("ファイルの読み込みに失敗しました。書式を確認してください。")
        return None
    try:
        return _standardize_sales_df(df)
    except ValueError as exc:
        st.error(str(exc))
    return None


def _yen_number_input(
    label: str,
    *,
    value: float,
    min_value: float = 0.0,
    max_value: float | None = None,
    step: float = 1.0,
    key: str | None = None,
    help: str | None = None,
) -> float:
    kwargs = {
        "min_value": float(min_value),
        "step": float(step),
        "value": float(value),
        "format": "¥%.0f",
    }
    if max_value is not None:
        kwargs["max_value"] = float(max_value)
    if key is not None:
        kwargs["key"] = key
    if help is not None:
        kwargs["help"] = help
    return float(st.number_input(label, **kwargs))


def _percent_number_input(
    label: str,
    *,
    value: float,
    min_value: float = 0.0,
    max_value: float = 1.0,
    step: float = 0.01,
    key: str | None = None,
    help: str | None = None,
) -> float:
    kwargs = {
        "min_value": float(min_value),
        "max_value": float(max_value),
        "step": float(step),
        "value": float(value),
        "format": "%.2f%%",
    }
    if key is not None:
        kwargs["key"] = key
    if help is not None:
        kwargs["help"] = help
    return float(st.number_input(label, **kwargs))


def _render_sales_guide_panel() -> None:
    st.markdown(
        """
        <div class="guide-panel" style="background-color:rgba(240,248,255,0.6);padding:1rem;border-radius:0.75rem;">
            <h4 style="margin-top:0;">💡 入力ガイド</h4>
            <ul style="padding-left:1.2rem;">
                <li title="例示による入力イメージ">チャネル×商品×月の例：<strong>オンライン販売 10万円</strong>、<strong>店舗販売 5万円</strong>のように具体的な数字から積み上げると精度が高まります。</li>
                <li title="売上＝客数×客単価×購入頻度">売上は <strong>客数×客単価×購入頻度</strong> に分解すると改善ポイントが見えます。</li>
                <li title="チャネル別の獲得効率を把握">チャネルごとに行を分け、獲得効率や投資対効果を比較しましょう。</li>
                <li title="商品ライフサイクルに応じた山谷を設定">商品ごとに月別の山谷を設定し、販促や季節性を織り込みます。</li>
                <li title="テンプレートはCSV/Excelでオフライン編集可能">テンプレートはダウンロードしてオフラインで編集し、同じ形式でアップロードできます。</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _sales_dataframe(data: Dict) -> pd.DataFrame:
    rows: List[Dict[str, float | str]] = []
    for item in data.get("items", []):
        row: Dict[str, float | str] = {
            "チャネル": item.get("channel", ""),
            "商品": item.get("product", ""),
        }
        monthly = item.get("monthly", {})
        amounts = monthly.get("amounts") if isinstance(monthly, dict) else None
        for idx, month in enumerate(MONTH_SEQUENCE, start=0):
            key = f"月{month:02d}"
            if isinstance(amounts, list):
                value = Decimal(str(amounts[idx])) if idx < len(amounts) else Decimal("0")
            elif isinstance(amounts, dict):
                value = Decimal(str(amounts.get(month, 0)))
            else:
                value = Decimal("0")
            row[key] = float(value)
        rows.append(row)
    if not rows:
        rows.append({"チャネル": "オンライン", "商品": "主力製品", **{f"月{m:02d}": 0.0 for m in MONTH_SEQUENCE}})
    df = pd.DataFrame(rows)
    return df


def _capex_dataframe(data: Dict) -> pd.DataFrame:
    items = data.get("items", [])
    if not items:
        return pd.DataFrame(
            [{"投資名": "新工場設備", "金額": 0.0, "開始月": 1, "耐用年数": 5}]
        )
    rows = []
    for item in items:
        rows.append(
            {
                "投資名": item.get("name", ""),
                "金額": float(Decimal(str(item.get("amount", 0)))),
                "開始月": int(item.get("start_month", 1)),
                "耐用年数": int(item.get("useful_life_years", 5)),
            }
        )
    return pd.DataFrame(rows)


def _loan_dataframe(data: Dict) -> pd.DataFrame:
    loans = data.get("loans", [])
    if not loans:
        return pd.DataFrame(
            [
                {
                    "名称": "メインバンク借入",
                    "元本": 0.0,
                    "金利": 0.01,
                    "返済期間(月)": 60,
                    "開始月": 1,
                    "返済タイプ": "equal_principal",
                }
            ]
        )
    rows = []
    for loan in loans:
        rows.append(
            {
                "名称": loan.get("name", ""),
                "元本": float(Decimal(str(loan.get("principal", 0)))),
                "金利": float(Decimal(str(loan.get("interest_rate", 0)))),
                "返済期間(月)": int(loan.get("term_months", 12)),
                "開始月": int(loan.get("start_month", 1)),
                "返済タイプ": loan.get("repayment_type", "equal_principal"),
            }
        )
    return pd.DataFrame(rows)


sales_defaults_df = _sales_dataframe(finance_raw.get("sales", {}))
_ensure_sales_template_state(sales_defaults_df)
stored_sales_df = st.session_state.get(SALES_TEMPLATE_STATE_KEY, sales_defaults_df)
try:
    sales_df = _standardize_sales_df(pd.DataFrame(stored_sales_df))
except ValueError:
    sales_df = sales_defaults_df.copy()
st.session_state[SALES_TEMPLATE_STATE_KEY] = sales_df

capex_defaults_df = _capex_dataframe(finance_raw.get("capex", {}))
loan_defaults_df = _loan_dataframe(finance_raw.get("loans", {}))

costs_defaults = finance_raw.get("costs", {})
variable_ratios = costs_defaults.get("variable_ratios", {})
fixed_costs = costs_defaults.get("fixed_costs", {})
noi_defaults = costs_defaults.get("non_operating_income", {})
noe_defaults = costs_defaults.get("non_operating_expenses", {})

tax_defaults = finance_raw.get("tax", {})

settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
unit = str(settings_state.get("unit", "百万円"))
unit_factor = UNIT_FACTORS.get(unit, Decimal("1"))


def _set_wizard_step(step_id: str) -> None:
    st.session_state[INPUT_WIZARD_STEP_KEY] = step_id


def _get_step_index(step_id: str) -> int:
    for idx, step in enumerate(WIZARD_STEPS):
        if step["id"] == step_id:
            return idx
    return 0


def _render_stepper(current_step: str) -> int:
    step_index = _get_step_index(current_step)
    progress_ratio = (step_index + 1) / len(WIZARD_STEPS)
    st.progress(progress_ratio, text=f"ステップ {step_index + 1} / {len(WIZARD_STEPS)}")
    labels: List[str] = []
    for idx, step in enumerate(WIZARD_STEPS):
        label = f"{idx + 1}. {step['title']}"
        if step["id"] == current_step:
            label = f"**{label}**"
        labels.append(label)
    st.markdown(" → ".join(labels))
    st.caption(WIZARD_STEPS[step_index]["description"])
    return step_index


def _render_navigation(step_index: int) -> None:
    prev_step_id = WIZARD_STEPS[step_index - 1]["id"] if step_index > 0 else None
    next_step_id = WIZARD_STEPS[step_index + 1]["id"] if step_index < len(WIZARD_STEPS) - 1 else None
    nav_cols = st.columns([1, 1, 6])
    with nav_cols[0]:
        if prev_step_id is not None:
            st.button(
                "← 戻る",
                use_container_width=True,
                on_click=_set_wizard_step,
                args=(prev_step_id,),
                key=f"prev_{step_index}",
            )
        else:
            st.markdown("&nbsp;")
    with nav_cols[1]:
        if next_step_id is not None:
            st.button(
                "次へ →",
                use_container_width=True,
                type="primary",
                on_click=_set_wizard_step,
                args=(next_step_id,),
                key=f"next_{step_index}",
            )
        else:
            st.markdown("&nbsp;")
    with nav_cols[2]:
        if next_step_id is not None:
            st.caption(f"次のステップ：{WIZARD_STEPS[step_index + 1]['title']}")
        else:
            st.caption("ウィザードの最後です。内容を保存しましょう。")


def _variable_inputs_from_state(defaults: Dict[str, object]) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for code, _, _ in VARIABLE_RATIO_FIELDS:
        key = f"var_ratio_{code}"
        default_value = float(defaults.get(code, 0.0))
        values[code] = float(st.session_state.get(key, default_value))
    return values


def _monetary_inputs_from_state(
    defaults: Dict[str, object],
    fields,
    prefix: str,
    unit_factor: Decimal,
) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for code, _, _ in fields:
        key = f"{prefix}_{code}"
        default_value = float(Decimal(str(defaults.get(code, 0.0))) / unit_factor)
        values[code] = float(st.session_state.get(key, default_value))
    return values


if INPUT_WIZARD_STEP_KEY not in st.session_state:
    st.session_state[INPUT_WIZARD_STEP_KEY] = WIZARD_STEPS[0]["id"]

if BUSINESS_CONTEXT_KEY not in st.session_state:
    st.session_state[BUSINESS_CONTEXT_KEY] = BUSINESS_CONTEXT_TEMPLATE.copy()
context_state: Dict[str, str] = st.session_state[BUSINESS_CONTEXT_KEY]

if "capex_editor_df" not in st.session_state:
    st.session_state["capex_editor_df"] = capex_defaults_df.copy()
if "loan_editor_df" not in st.session_state:
    st.session_state["loan_editor_df"] = loan_defaults_df.copy()

for code, _, _ in VARIABLE_RATIO_FIELDS:
    st.session_state.setdefault(f"var_ratio_{code}", float(variable_ratios.get(code, 0.0)))
for code, _, _ in FIXED_COST_FIELDS:
    default_value = float(Decimal(str(fixed_costs.get(code, 0.0))) / unit_factor)
    st.session_state.setdefault(f"fixed_cost_{code}", default_value)
for code, _, _ in NOI_FIELDS:
    default_value = float(Decimal(str(noi_defaults.get(code, 0.0))) / unit_factor)
    st.session_state.setdefault(f"noi_{code}", default_value)
for code, _, _ in NOE_FIELDS:
    default_value = float(Decimal(str(noe_defaults.get(code, 0.0))) / unit_factor)
    st.session_state.setdefault(f"noe_{code}", default_value)

st.session_state.setdefault("tax_corporate_rate", float(tax_defaults.get("corporate_tax_rate", 0.3)))
st.session_state.setdefault("tax_consumption_rate", float(tax_defaults.get("consumption_tax_rate", 0.1)))
st.session_state.setdefault("tax_dividend_ratio", float(tax_defaults.get("dividend_payout_ratio", 0.0)))

current_step = str(st.session_state[INPUT_WIZARD_STEP_KEY])

st.title("🧾 データ入力ハブ")
st.caption("ウィザード形式で売上から投資までを順番に整理します。保存すると全ページに反映されます。")

st.sidebar.title("📘 ヘルプセンター")
with st.sidebar.expander("よくある質問 (FAQ)", expanded=False):
    st.markdown(
        """
        **Q. 売上計画はどの程度細かく分類すべきですか？**  \\
        A. 改善アクションを検討できる単位（チャネル×商品など）での分解を推奨します。\\
        \\
        **Q. 数値がまだ固まっていない場合は？**  \\
        A. 過去実績や他社事例から仮置きし、コメント欄に前提条件をメモすると更新が楽になります。\\
        \\
        **Q. 入力途中で別ステップに移動しても大丈夫？**  \\
        A. 各ステップは自動保存されます。最終的に「保存」を押すと財務計画に反映されます。
        """
    )
with st.sidebar.expander("用語集", expanded=False):
    st.markdown(
        """
        - **粗利益率**： (売上 − 売上原価) ÷ 売上。製造業では30%超が目安。\\
        - **変動費**： 売上に比例して増減する費用。材料費や外注費など。\\
        - **固定費**： 毎月一定で発生する費用。人件費や家賃など。\\
        - **CAPEX**： 設備投資。長期にわたり利用する資産の購入費用。\\
        - **借入金**： 金融機関等からの調達。金利と返済期間を設定します。
        """
    )
st.sidebar.info("入力途中でもステップを行き来できます。最終ステップで保存すると数値が確定します。")

step_index = _render_stepper(current_step)

if current_step == "context":
    st.header("STEP 1｜ビジネスモデル整理")
    st.markdown("3C分析とビジネスモデルキャンバスの主要要素を整理して、数値入力の前提を明確にしましょう。")
    st.info("顧客(Customer)・自社(Company)・競合(Competitor)の視点を1〜2行でも言語化することで、収益モデルの仮定がぶれにくくなります。")

    three_c_cols = st.columns(3)
    with three_c_cols[0]:
        context_state["three_c_customer"] = st.text_area(
            "Customer（顧客）",
            value=context_state.get("three_c_customer", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["three_c_customer"],
            help="想定顧客層や顧客課題を記入してください。",
            height=150,
        )
    with three_c_cols[1]:
        context_state["three_c_company"] = st.text_area(
            "Company（自社）",
            value=context_state.get("three_c_company", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["three_c_company"],
            help="自社の強み・提供価値・リソースを整理しましょう。",
            height=150,
        )
    with three_c_cols[2]:
        context_state["three_c_competitor"] = st.text_area(
            "Competitor（競合）",
            value=context_state.get("three_c_competitor", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["three_c_competitor"],
            help="競合の特徴や比較したときの優位性・弱点を記入します。",
            height=150,
        )

    st.markdown("#### ビジネスモデルキャンバス（主要要素）")
    bmc_cols = st.columns(3)
    with bmc_cols[0]:
        context_state["bmc_customer_segments"] = st.text_area(
            "顧客セグメント",
            value=context_state.get("bmc_customer_segments", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["bmc_customer_segments"],
            help="年齢・職種・企業規模など、ターゲット顧客の解像度を高めましょう。",
            height=160,
        )
    with bmc_cols[1]:
        context_state["bmc_value_proposition"] = st.text_area(
            "提供価値",
            value=context_state.get("bmc_value_proposition", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["bmc_value_proposition"],
            help="顧客課題をどのように解決するか、成功事例なども記載すると有効です。",
            height=160,
        )
    with bmc_cols[2]:
        context_state["bmc_channels"] = st.text_area(
            "チャネル",
            value=context_state.get("bmc_channels", ""),
            placeholder=BUSINESS_CONTEXT_PLACEHOLDER["bmc_channels"],
            help="オンライン・オフラインの接点や販売フローを整理してください。",
            height=160,
        )

    context_state["qualitative_memo"] = st.text_area(
        "事業計画メモ",
        value=context_state.get("qualitative_memo", ""),
        placeholder=BUSINESS_CONTEXT_PLACEHOLDER["qualitative_memo"],
        help="KGI/KPIの設定根拠、注意点、投資判断に必要な情報などを自由に記入できます。",
        height=140,
    )
    st.caption("※ 記入した内容はウィザード内で保持され、事業計画書作成時の定性情報として活用できます。")

elif current_step == "sales":
    st.header("STEP 2｜売上計画")
    st.markdown("顧客セグメントとチャネルの整理結果をもとに、チャネル×商品×月で売上を見積もります。")
    st.info("例：オンライン販売 10万円、店舗販売 5万円など具体的な数字から積み上げると精度が高まります。季節性やプロモーション施策も織り込みましょう。")

    main_col, guide_col = st.columns([4, 1], gap="large")

    with main_col:
        control_cols = st.columns([1.2, 1.8, 1], gap="medium")
        with control_cols[0]:
            if st.button("チャネル追加", use_container_width=True, key="add_channel_button"):
                next_channel_idx = int(st.session_state.get(SALES_CHANNEL_COUNTER_KEY, 1))
                next_product_idx = int(st.session_state.get(SALES_PRODUCT_COUNTER_KEY, 1))
                new_row = {
                    "チャネル": f"新チャネル{next_channel_idx}",
                    "商品": f"新商品{next_product_idx}",
                    **{month: 0.0 for month in MONTH_COLUMNS},
                }
                st.session_state[SALES_CHANNEL_COUNTER_KEY] = next_channel_idx + 1
                st.session_state[SALES_PRODUCT_COUNTER_KEY] = next_product_idx + 1
                updated = pd.concat([sales_df, pd.DataFrame([new_row])], ignore_index=True)
                st.session_state[SALES_TEMPLATE_STATE_KEY] = _standardize_sales_df(updated)
                st.toast("新しいチャネル行を追加しました。", icon="➕")

        channel_options = [str(ch) for ch in sales_df["チャネル"].tolist() if str(ch).strip()]
        if not channel_options:
            channel_options = [f"新チャネル{int(st.session_state.get(SALES_CHANNEL_COUNTER_KEY, 1))}"]
        with control_cols[1]:
            selected_channel = st.selectbox(
                "商品追加先チャネル",
                options=channel_options,
                key="product_channel_select",
                help="商品を追加するチャネルを選択します。",
            )
        with control_cols[2]:
            if st.button("商品追加", use_container_width=True, key="add_product_button"):
                next_product_idx = int(st.session_state.get(SALES_PRODUCT_COUNTER_KEY, 1))
                target_channel = selected_channel or channel_options[0]
                new_row = {
                    "チャネル": target_channel,
                    "商品": f"新商品{next_product_idx}",
                    **{month: 0.0 for month in MONTH_COLUMNS},
                }
                st.session_state[SALES_PRODUCT_COUNTER_KEY] = next_product_idx + 1
                updated = pd.concat([sales_df, pd.DataFrame([new_row])], ignore_index=True)
                st.session_state[SALES_TEMPLATE_STATE_KEY] = _standardize_sales_df(updated)
                st.toast("選択したチャネルに商品行を追加しました。", icon="🆕")

        sales_df = st.session_state[SALES_TEMPLATE_STATE_KEY]
        month_columns_config = {
            month: st.column_config.NumberColumn(
                month,
                min_value=0.0,
                step=1.0,
                format="¥%d",
                help="月別の売上金額を入力します。",
            )
            for month in MONTH_COLUMNS
        }
        with st.form("sales_template_form"):
            download_cols = st.columns(2)
            with download_cols[0]:
                st.download_button(
                    "CSVテンプレートDL",
                    data=_sales_template_to_csv(sales_df),
                    file_name="sales_template.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with download_cols[1]:
                st.download_button(
                    "ExcelテンプレートDL",
                    data=_sales_template_to_excel(sales_df),
                    file_name="sales_template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            uploaded_template = st.file_uploader(
                "テンプレートをアップロード (最大5MB)",
                type=["csv", "xlsx"],
                accept_multiple_files=False,
                help="ダウンロードしたテンプレートと同じ列構成でアップロードしてください。",
            )
            edited_df = st.data_editor(
                sales_df,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "チャネル": st.column_config.TextColumn("チャネル", max_chars=40, help="販売経路（例：自社EC、店舗など）"),
                    "商品": st.column_config.TextColumn("商品", max_chars=40, help="商品・サービス名を入力します。"),
                    **month_columns_config,
                },
                key="sales_editor",
            )
            if st.form_submit_button("テンプレートを反映", use_container_width=True):
                if uploaded_template is not None:
                    loaded_df = _load_sales_template_from_upload(uploaded_template)
                    if loaded_df is not None:
                        st.session_state[SALES_TEMPLATE_STATE_KEY] = loaded_df
                        st.success("アップロードしたテンプレートを適用しました。")
                else:
                    st.session_state[SALES_TEMPLATE_STATE_KEY] = _standardize_sales_df(
                        pd.DataFrame(edited_df)
                    )
                    st.success("エディタの内容をテンプレートに反映しました。")

        sales_df = st.session_state[SALES_TEMPLATE_STATE_KEY]
        if any(err.field.startswith("sales") for err in validation_errors):
            messages = "<br/>".join(
                err.message for err in validation_errors if err.field.startswith("sales")
            )
            st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)

    with guide_col:
        _render_sales_guide_panel()

elif current_step == "costs":
    st.header("STEP 3｜原価・経費")
    st.markdown("売上に対する変動費（原価）と固定費、営業外項目を入力し、粗利益率の前提を確認します。")
    st.info("粗利益率＝(売上−売上原価)÷売上。製造業では30%を超えると優良とされます。目標レンジと比較しながら設定しましょう。")

    st.markdown("#### 変動費（原価率）")
    var_cols = st.columns(len(VARIABLE_RATIO_FIELDS))
    variable_inputs: Dict[str, float] = {}
    for col, (code, label, help_text) in zip(var_cols, VARIABLE_RATIO_FIELDS):
        with col:
            variable_inputs[code] = _percent_number_input(
                label,
                min_value=0.0,
                max_value=1.0,
                step=0.005,
                value=float(variable_ratios.get(code, 0.0)),
                key=f"var_ratio_{code}",
                help=help_text,
            )
    st.caption("※ 原価率は売上高に対する比率で入力します。0〜100%の範囲で設定してください。")

    st.markdown("#### 固定費（販管費）")
    fixed_cols = st.columns(len(FIXED_COST_FIELDS))
    fixed_inputs: Dict[str, float] = {}
    for col, (code, label, help_text) in zip(fixed_cols, FIXED_COST_FIELDS):
        with col:
            base_value = Decimal(str(fixed_costs.get(code, 0.0)))
            fixed_inputs[code] = _yen_number_input(
                f"{label} ({unit})",
                value=float(base_value / unit_factor),
                step=1.0,
                key=f"fixed_cost_{code}",
                help=help_text,
            )
    st.caption("※ 表示単位に合わせた金額で入力します。採用計画やコスト削減メモは事業計画メモ欄へ。")

    st.markdown("#### 営業外収益 / 営業外費用")
    noi_cols = st.columns(len(NOI_FIELDS))
    noi_inputs: Dict[str, float] = {}
    for col, (code, label, help_text) in zip(noi_cols, NOI_FIELDS):
        with col:
            base_value = Decimal(str(noi_defaults.get(code, 0.0)))
            noi_inputs[code] = _yen_number_input(
                f"{label} ({unit})",
                value=float(base_value / unit_factor),
                step=1.0,
                key=f"noi_{code}",
                help=help_text,
            )

    noe_cols = st.columns(len(NOE_FIELDS))
    noe_inputs: Dict[str, float] = {}
    for col, (code, label, help_text) in zip(noe_cols, NOE_FIELDS):
        with col:
            base_value = Decimal(str(noe_defaults.get(code, 0.0)))
            noe_inputs[code] = _yen_number_input(
                f"{label} ({unit})",
                value=float(base_value / unit_factor),
                step=1.0,
                key=f"noe_{code}",
                help=help_text,
            )

    if any(err.field.startswith("costs") for err in validation_errors):
        messages = "<br/>".join(
            err.message for err in validation_errors if err.field.startswith("costs")
        )
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)

elif current_step == "invest":
    st.header("STEP 4｜投資・借入")
    st.markdown("成長投資や資金調達のスケジュールを設定します。金額・開始月・耐用年数を明確にしましょう。")
    st.info("投資額は税込・税抜どちらでも構いませんが、他データと整合するよう統一します。借入は金利・返済期間・開始月をセットで管理しましょう。")

    st.markdown("#### 設備投資 (Capex)")
    current_capex_df = pd.DataFrame(st.session_state.get("capex_editor_df", capex_defaults_df))
    capex_editor_df = st.data_editor(
        current_capex_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "投資名": st.column_config.TextColumn("投資名", help="投資対象の名称を入力します。"),
            "金額": st.column_config.NumberColumn(
                "金額 (円)",
                min_value=0.0,
                step=1_000_000.0,
                format="¥%d",
                help="投資にかかる総額。例：5,000,000円など。",
            ),
            "開始月": st.column_config.NumberColumn(
                "開始月",
                min_value=1,
                max_value=12,
                step=1,
                help="設備が稼働を開始する月。",
            ),
            "耐用年数": st.column_config.NumberColumn(
                "耐用年数 (年)",
                min_value=1,
                max_value=20,
                step=1,
                help="減価償却に用いる耐用年数を入力します。",
            ),
        },
        key="capex_editor",
    )
    st.session_state["capex_editor_df"] = capex_editor_df
    st.caption("例：新工場設備 5,000,000円を4月開始、耐用年数5年 など。")

    st.markdown("#### 借入スケジュール")
    current_loan_df = pd.DataFrame(st.session_state.get("loan_editor_df", loan_defaults_df))
    loan_editor_df = st.data_editor(
        current_loan_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "名称": st.column_config.TextColumn("名称", help="借入の名称（例：メインバンク、リースなど）。"),
            "元本": st.column_config.NumberColumn(
                "元本 (円)",
                min_value=0.0,
                step=1_000_000.0,
                format="¥%d",
                help="借入金額の総額。",
            ),
            "金利": st.column_config.NumberColumn(
                "金利",
                min_value=0.0,
                max_value=0.2,
                step=0.001,
                format="%.2f%%",
                help="年利ベースの金利を入力します。",
            ),
            "返済期間(月)": st.column_config.NumberColumn(
                "返済期間 (月)",
                min_value=1,
                max_value=600,
                step=1,
                help="返済回数（月数）。",
            ),
            "開始月": st.column_config.NumberColumn(
                "開始月",
                min_value=1,
                max_value=12,
                step=1,
                help="返済開始月。",
            ),
            "返済タイプ": st.column_config.SelectboxColumn(
                "返済タイプ",
                options=["equal_principal", "interest_only"],
                help="元金均等（equal_principal）か利息のみ（interest_only）かを選択。",
            ),
        },
        key="loan_editor",
    )
    st.session_state["loan_editor_df"] = loan_editor_df

    if any(err.field.startswith("capex") for err in validation_errors):
        messages = "<br/>".join(
            err.message for err in validation_errors if err.field.startswith("capex")
        )
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)
    if any(err.field.startswith("loans") for err in validation_errors):
        messages = "<br/>".join(
            err.message for err in validation_errors if err.field.startswith("loans")
        )
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)

elif current_step == "tax":
    st.header("STEP 5｜税制・保存")
    st.markdown("税率を確認し、これまでの入力内容を保存します。")
    st.info("法人税率・消費税率・配当性向は業種や制度により異なります。最新情報を確認しながら設定してください。")

    tax_cols = st.columns(3)
    with tax_cols[0]:
        corporate_rate = _percent_number_input(
            "法人税率 (0-55%)",
            min_value=0.0,
            max_value=0.55,
            step=0.01,
            value=float(st.session_state.get("tax_corporate_rate", 0.3)),
            key="tax_corporate_rate",
            help=TAX_FIELD_META["corporate"],
        )
    with tax_cols[1]:
        consumption_rate = _percent_number_input(
            "消費税率 (0-20%)",
            min_value=0.0,
            max_value=0.20,
            step=0.01,
            value=float(st.session_state.get("tax_consumption_rate", 0.1)),
            key="tax_consumption_rate",
            help=TAX_FIELD_META["consumption"],
        )
    with tax_cols[2]:
        dividend_ratio = _percent_number_input(
            "配当性向",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            value=float(st.session_state.get("tax_dividend_ratio", 0.0)),
            key="tax_dividend_ratio",
            help=TAX_FIELD_META["dividend"],
        )

    sales_df = _standardize_sales_df(pd.DataFrame(st.session_state[SALES_TEMPLATE_STATE_KEY]))
    total_sales = sum(
        Decimal(str(row[month])) for _, row in sales_df.iterrows() for month in MONTH_COLUMNS
    )
    current_variable_inputs = _variable_inputs_from_state(variable_ratios)
    avg_ratio = (
        sum(current_variable_inputs.values()) / len(current_variable_inputs)
        if current_variable_inputs
        else 0.0
    )

    metric_cols = st.columns(2)
    with metric_cols[0]:
        st.markdown(
            f"<div class='metric-card' title='年間のチャネル×商品売上の合計額です。'>📊 <strong>売上合計</strong><br/><span style='font-size:1.4rem;'>{format_amount_with_unit(total_sales, unit)}</span></div>",
            unsafe_allow_html=True,
        )
    with metric_cols[1]:
        st.markdown(
            f"<div class='metric-card' title='粗利益率＝(売上−売上原価)÷売上。製造業では30%を超えると優良とされます。'>📊 <strong>平均原価率</strong><br/><span style='font-size:1.4rem;'>{format_ratio(avg_ratio)}</span></div>",
            unsafe_allow_html=True,
        )

    if validation_errors:
        st.warning("入力内容にエラーがあります。該当ステップに戻って赤枠の項目を修正してください。")

    costs_variable_inputs = _variable_inputs_from_state(variable_ratios)
    costs_fixed_inputs = _monetary_inputs_from_state(
        fixed_costs, FIXED_COST_FIELDS, "fixed_cost", unit_factor
    )
    costs_noi_inputs = _monetary_inputs_from_state(
        noi_defaults, NOI_FIELDS, "noi", unit_factor
    )
    costs_noe_inputs = _monetary_inputs_from_state(
        noe_defaults, NOE_FIELDS, "noe", unit_factor
    )

    save_col, _ = st.columns([2, 1])
    with save_col:
        if st.button("入力を検証して保存", type="primary", use_container_width=True):
            sales_df = _standardize_sales_df(pd.DataFrame(st.session_state[SALES_TEMPLATE_STATE_KEY]))
            st.session_state[SALES_TEMPLATE_STATE_KEY] = sales_df

            sales_data = {"items": []}
            for _, row in sales_df.fillna(0).iterrows():
                monthly_amounts = [Decimal(str(row[month])) for month in MONTH_COLUMNS]
                sales_data["items"].append(
                    {
                        "channel": str(row.get("チャネル", "")).strip() or "未設定",
                        "product": str(row.get("商品", "")).strip() or "未設定",
                        "monthly": {"amounts": monthly_amounts},
                    }
                )

            costs_data = {
                "variable_ratios": {
                    code: Decimal(str(value)) for code, value in costs_variable_inputs.items()
                },
                "fixed_costs": {
                    code: Decimal(str(value)) * unit_factor for code, value in costs_fixed_inputs.items()
                },
                "non_operating_income": {
                    code: Decimal(str(value)) * unit_factor for code, value in costs_noi_inputs.items()
                },
                "non_operating_expenses": {
                    code: Decimal(str(value)) * unit_factor for code, value in costs_noe_inputs.items()
                },
            }

            capex_df = pd.DataFrame(st.session_state.get("capex_editor_df", capex_defaults_df))
            capex_data = {
                "items": [
                    {
                        "name": ("" if pd.isna(row.get("投資名", "")) else str(row.get("投資名", ""))).strip()
                        or "未設定",
                        "amount": Decimal(
                            str(row.get("金額", 0) if not pd.isna(row.get("金額", 0)) else 0)
                        ),
                        "start_month": int(
                            row.get("開始月", 1) if not pd.isna(row.get("開始月", 1)) else 1
                        ),
                        "useful_life_years": int(
                            row.get("耐用年数", 5) if not pd.isna(row.get("耐用年数", 5)) else 5
                        ),
                    }
                    for _, row in capex_df.iterrows()
                    if Decimal(
                        str(row.get("金額", 0) if not pd.isna(row.get("金額", 0)) else 0)
                    )
                    > 0
                ]
            }

            loan_df = pd.DataFrame(st.session_state.get("loan_editor_df", loan_defaults_df))
            loan_data = {
                "loans": [
                    {
                        "name": ("" if pd.isna(row.get("名称", "")) else str(row.get("名称", ""))).strip()
                        or "借入",
                        "principal": Decimal(
                            str(row.get("元本", 0) if not pd.isna(row.get("元本", 0)) else 0)
                        ),
                        "interest_rate": Decimal(
                            str(row.get("金利", 0) if not pd.isna(row.get("金利", 0)) else 0)
                        ),
                        "term_months": int(
                            row.get("返済期間(月)", 12)
                            if not pd.isna(row.get("返済期間(月)", 12))
                            else 12
                        ),
                        "start_month": int(
                            row.get("開始月", 1) if not pd.isna(row.get("開始月", 1)) else 1
                        ),
                        "repayment_type": (
                            row.get("返済タイプ", "equal_principal")
                            if row.get("返済タイプ", "equal_principal")
                            in {"equal_principal", "interest_only"}
                            else "equal_principal"
                        ),
                    }
                    for _, row in loan_df.iterrows()
                    if Decimal(
                        str(row.get("元本", 0) if not pd.isna(row.get("元本", 0)) else 0)
                    )
                    > 0
                ]
            }

            tax_data = {
                "corporate_tax_rate": Decimal(str(corporate_rate)),
                "consumption_tax_rate": Decimal(str(consumption_rate)),
                "dividend_payout_ratio": Decimal(str(dividend_ratio)),
            }

            bundle_dict = {
                "sales": sales_data,
                "costs": costs_data,
                "capex": capex_data,
                "loans": loan_data,
                "tax": tax_data,
            }

            bundle, issues = validate_bundle(bundle_dict)
            if issues:
                st.session_state["finance_validation_errors"] = issues
                st.toast("入力にエラーがあります。赤枠の項目を修正してください。", icon="❌")
            else:
                st.session_state["finance_validation_errors"] = []
                st.session_state["finance_raw"] = bundle_dict
                st.session_state["finance_models"] = {
                    "sales": bundle.sales,
                    "costs": bundle.costs,
                    "capex": bundle.capex,
                    "loans": bundle.loans,
                    "tax": bundle.tax,
                }
                st.toast("財務データを保存しました。", icon="✅")

st.session_state[BUSINESS_CONTEXT_KEY] = context_state
_render_navigation(step_index)
