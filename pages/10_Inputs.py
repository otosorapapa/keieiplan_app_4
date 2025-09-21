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
) -> float:
    kwargs = {"min_value": float(min_value), "step": float(step), "value": float(value), "format": "¥%.0f"}
    if max_value is not None:
        kwargs["max_value"] = float(max_value)
    if key is not None:
        kwargs["key"] = key
    return float(st.number_input(label, **kwargs))


def _percent_number_input(
    label: str,
    *,
    value: float,
    min_value: float = 0.0,
    max_value: float = 1.0,
    step: float = 0.01,
    key: str | None = None,
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
    return float(st.number_input(label, **kwargs))


def _render_sales_guide_panel() -> None:
    st.markdown(
        """
        <div class="guide-panel" style="background-color:rgba(240,248,255,0.6);padding:1rem;border-radius:0.75rem;">
            <h4 style="margin-top:0;">💡 入力ガイド</h4>
            <ul style="padding-left:1.2rem;">
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


sales_base_df = _sales_dataframe(finance_raw.get("sales", {}))
_ensure_sales_template_state(sales_base_df)
stored_sales_df = st.session_state.get(SALES_TEMPLATE_STATE_KEY, sales_base_df)
try:
    sales_df = _standardize_sales_df(pd.DataFrame(stored_sales_df))
except ValueError:
    sales_df = sales_base_df.copy()
st.session_state[SALES_TEMPLATE_STATE_KEY] = sales_df
capex_df = _capex_dataframe(finance_raw.get("capex", {}))
loan_df = _loan_dataframe(finance_raw.get("loans", {}))

costs_defaults = finance_raw.get("costs", {})
variable_ratios = costs_defaults.get("variable_ratios", {})
fixed_costs = costs_defaults.get("fixed_costs", {})
noi_defaults = costs_defaults.get("non_operating_income", {})
noe_defaults = costs_defaults.get("non_operating_expenses", {})

settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
unit = str(settings_state.get("unit", "百万円"))
unit_factor = UNIT_FACTORS.get(unit, Decimal("1"))

st.title("🧾 データ入力ハブ")
st.caption("売上からコスト、投資、借入、税制までを一箇所で整理します。保存すると全ページに反映されます。")

sales_tab, cost_tab, invest_tab, tax_tab = st.tabs(
    ["売上計画", "コスト計画", "投資・借入", "税制・メモ"]
)

with sales_tab:
    st.subheader("売上計画：チャネル×商品×月")
    st.caption("各行はチャネル×商品を表し、12ヶ月の売上高を入力します。テンプレートをDL/ULすると、オフライン編集も可能です。")

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
            month: st.column_config.NumberColumn(month, min_value=0.0, step=1.0, format="¥%d")
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
                    "チャネル": st.column_config.TextColumn("チャネル", max_chars=40),
                    "商品": st.column_config.TextColumn("商品", max_chars=40),
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

with cost_tab:
    st.subheader("コスト計画：変動費と固定費")
    var_cols = st.columns(5)
    var_codes = ["COGS_MAT", "COGS_LBR", "COGS_OUT_SRC", "COGS_OUT_CON", "COGS_OTH"]
    var_labels = ["材料費", "外部労務費", "外注費(専属)", "外注費(委託)", "その他原価"]
    variable_inputs: Dict[str, float] = {}
    for col, code, label in zip(var_cols, var_codes, var_labels):
        with col:
            variable_inputs[code] = _percent_number_input(
                f"{label} 原価率",
                min_value=0.0,
                max_value=1.0,
                step=0.005,
                value=float(variable_ratios.get(code, 0.0)),
            )
    st.caption("変動費は売上高に対する比率で入力します。0〜1の範囲で設定してください。")

    fixed_cols = st.columns(3)
    fixed_codes = ["OPEX_H", "OPEX_K", "OPEX_DEP"]
    fixed_labels = ["人件費", "経費", "減価償却"]
    fixed_inputs: Dict[str, float] = {}
    for col, code, label in zip(fixed_cols, fixed_codes, fixed_labels):
        with col:
            base_value = Decimal(str(fixed_costs.get(code, 0.0)))
            fixed_inputs[code] = _yen_number_input(
                f"{label} ({unit})",
                value=float(base_value / unit_factor),
                step=1.0,
            )
    st.caption("固定費は入力した単位で保存されます。")

    st.markdown("#### 営業外収益 / 営業外費用")
    noi_cols = st.columns(3)
    noi_codes = ["NOI_MISC", "NOI_GRANT", "NOI_OTH"]
    noi_labels = ["雑収入", "補助金", "その他"]
    noi_inputs: Dict[str, float] = {}
    for col, code, label in zip(noi_cols, noi_codes, noi_labels):
        with col:
            base_value = Decimal(str(noi_defaults.get(code, 0.0)))
            noi_inputs[code] = _yen_number_input(
                f"{label} ({unit})",
                value=float(base_value / unit_factor),
                step=1.0,
            )

    noe_cols = st.columns(2)
    noe_codes = ["NOE_INT", "NOE_OTH"]
    noe_labels = ["支払利息", "その他費用"]
    noe_inputs: Dict[str, float] = {}
    for col, code, label in zip(noe_cols, noe_codes, noe_labels):
        with col:
            base_value = Decimal(str(noe_defaults.get(code, 0.0)))
            noe_inputs[code] = _yen_number_input(
                f"{label} ({unit})",
                value=float(base_value / unit_factor),
                step=1.0,
            )

    if any(err.field.startswith("costs") for err in validation_errors):
        messages = "<br/>".join(err.message for err in validation_errors if err.field.startswith("costs"))
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)

with invest_tab:
    st.subheader("投資・借入計画")
    st.markdown("#### 設備投資 (Capex)")
    capex_df = st.data_editor(
        capex_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "金額": st.column_config.NumberColumn(
                "金額 (円)", min_value=0.0, step=1_000_000.0, format="¥%d"
            ),
            "開始月": st.column_config.NumberColumn("開始月", min_value=1, max_value=12, step=1),
            "耐用年数": st.column_config.NumberColumn("耐用年数 (年)", min_value=1, max_value=20, step=1),
        },
        key="capex_editor",
    )

    st.markdown("#### 借入スケジュール")
    loan_df = st.data_editor(
        loan_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "元本": st.column_config.NumberColumn(
                "元本 (円)", min_value=0.0, step=1_000_000.0, format="¥%d"
            ),
            "金利": st.column_config.NumberColumn(
                "金利", min_value=0.0, max_value=0.2, step=0.001, format="%.2f%%"
            ),
            "返済期間(月)": st.column_config.NumberColumn("返済期間 (月)", min_value=1, max_value=600, step=1),
            "開始月": st.column_config.NumberColumn("開始月", min_value=1, max_value=12, step=1),
            "返済タイプ": st.column_config.SelectboxColumn("返済タイプ", options=["equal_principal", "interest_only"]),
        },
        key="loan_editor",
    )

    if any(err.field.startswith("capex") for err in validation_errors):
        messages = "<br/>".join(err.message for err in validation_errors if err.field.startswith("capex"))
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)
    if any(err.field.startswith("loans") for err in validation_errors):
        messages = "<br/>".join(err.message for err in validation_errors if err.field.startswith("loans"))
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)

with tax_tab:
    st.subheader("税制・備考")
    tax_defaults = finance_raw.get("tax", {})
    corporate_rate = _percent_number_input(
        "法人税率 (0-55%)",
        min_value=0.0,
        max_value=0.55,
        step=0.01,
        value=float(tax_defaults.get("corporate_tax_rate", 0.3)),
    )
    consumption_rate = _percent_number_input(
        "消費税率 (0-20%)",
        min_value=0.0,
        max_value=0.20,
        step=0.01,
        value=float(tax_defaults.get("consumption_tax_rate", 0.1)),
    )
    dividend_ratio = _percent_number_input(
        "配当性向",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
        value=float(tax_defaults.get("dividend_payout_ratio", 0.0)),
    )

    st.caption("税率は自動でバリデーションされます。")

    if any(err.field.startswith("tax") for err in validation_errors):
        messages = "<br/>".join(err.message for err in validation_errors if err.field.startswith("tax"))
        st.markdown(f"<div class='field-error'>{messages}</div>", unsafe_allow_html=True)


save_col, summary_col = st.columns([2, 1])
with save_col:
    if st.button("入力を検証して保存", type="primary"):
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
            "variable_ratios": {code: Decimal(str(value)) for code, value in variable_inputs.items()},
            "fixed_costs": {code: Decimal(str(value)) * unit_factor for code, value in fixed_inputs.items()},
            "non_operating_income": {code: Decimal(str(value)) * unit_factor for code, value in noi_inputs.items()},
            "non_operating_expenses": {code: Decimal(str(value)) * unit_factor for code, value in noe_inputs.items()},
        }

        capex_data = {
            "items": [
                {
                    "name": ("" if pd.isna(row.get("投資名", "")) else str(row.get("投資名", ""))).strip()
                    or "未設定",
                    "amount": Decimal(str(row.get("金額", 0) if not pd.isna(row.get("金額", 0)) else 0)),
                    "start_month": int(row.get("開始月", 1) if not pd.isna(row.get("開始月", 1)) else 1),
                    "useful_life_years": int(row.get("耐用年数", 5) if not pd.isna(row.get("耐用年数", 5)) else 5),
                }
                for _, row in capex_df.iterrows()
                if Decimal(str(row.get("金額", 0) if not pd.isna(row.get("金額", 0)) else 0)) > 0
            ]
        }

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
                        if row.get("返済タイプ", "equal_principal") in {"equal_principal", "interest_only"}
                        else "equal_principal"
                    ),
                }
                for _, row in loan_df.iterrows()
                if Decimal(str(row.get("元本", 0) if not pd.isna(row.get("元本", 0)) else 0)) > 0
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

with summary_col:
    total_sales = sum(
        Decimal(str(row[month])) for _, row in sales_df.iterrows() for month in MONTH_COLUMNS
    )
    avg_ratio = sum(variable_inputs.values()) / len(variable_inputs) if variable_inputs else 0.0
    st.metric("売上合計", format_amount_with_unit(total_sales, unit))
    st.metric("平均原価率", format_ratio(avg_ratio))
