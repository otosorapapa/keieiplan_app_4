"""Report export page for PDF / Excel / Word outputs."""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, List, Sequence, Tuple, TypeVar

import pandas as pd
import streamlit as st
from docx import Document
from docx.shared import Inches
import matplotlib.pyplot as plt
from openpyxl.drawing.image import Image as ExcelImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image as PlatypusImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from ui.streamlit_compat import use_container_width_kwargs

from calc import compute, generate_cash_flow, plan_from_models, summarize_plan_metrics
from formatting import format_amount_with_unit, format_ratio
from state import ensure_session_defaults, load_finance_bundle
from theme import THEME_COLORS, inject_theme

st.set_page_config(
    page_title="経営計画スタジオ｜レポート",
    page_icon="報",
    layout="wide",
)

inject_theme()
ensure_session_defaults()

settings_state: Dict[str, object] = st.session_state.get("finance_settings", {})
unit = str(settings_state.get("unit", "百万円"))
fte = Decimal(str(settings_state.get("fte", 20)))
fiscal_year = int(settings_state.get("fiscal_year", 2025))

bundle, has_custom_inputs = load_finance_bundle()
if not has_custom_inputs:
    st.info("入力データが未保存のため、既定値でレポートを生成します。")

plan_cfg = plan_from_models(
    bundle.sales,
    bundle.costs,
    bundle.capex,
    bundle.loans,
    bundle.tax,
    fte=fte,
    unit=unit,
)

amounts = compute(plan_cfg)
metrics = summarize_plan_metrics(amounts)
cash_flow_data = generate_cash_flow(amounts, bundle.capex, bundle.loans, bundle.tax)

st.title("レポート出力")
st.caption("主要指標とKPIのサマリーをPDF / Excel / Word形式でダウンロードできます。")

SUPPORT_CONTACT = "support@keieiplan.jp"
PDF_FONT_NAME = "HeiseiKakuGo-W5"
T = TypeVar("T")


@dataclass(frozen=True)
class ReportSectionMeta:
    key: str
    title: str
    description: str
    note: str | None = None
    aria_label: str | None = None


REPORT_SECTION_ORDER: Tuple[ReportSectionMeta, ...] = (
    ReportSectionMeta(
        key="損益計画",
        title="損益計画（損益計算書フォーマット）",
        description="売上高から税引後利益までを日本政策金融公庫の様式に合わせて整理します。",
        note="売上高・売上原価・販管費・営業外収支・税引後利益を既定の並びと注記で整理しています。",
        aria_label="損益計画表",
    ),
    ReportSectionMeta(
        key="資金繰り表",
        title="資金繰り表",
        description="営業・投資・財務キャッシュフローを金融機関審査用の切り口で一覧化します。",
        note="営業・投資・財務キャッシュの区分とキャッシュ増減・減価償却を併記し資金繰りを確認できます。",
        aria_label="資金繰り表",
    ),
    ReportSectionMeta(
        key="投資計画",
        title="投資計画（設備投資内訳）",
        description="主要な投資案件を開始月・耐用年数・償却額とともに一覧化します。",
        note="各投資ごとに年間減価償却額を算出し、資金使途の根拠として提示します。",
        aria_label="投資計画一覧",
    ),
)
REPORT_SECTION_LOOKUP: Dict[str, ReportSectionMeta] = {
    section.key: section for section in REPORT_SECTION_ORDER
}
REPORT_SECTIONS: Sequence[str] = tuple(section.key for section in REPORT_SECTION_ORDER)


def _safe_ratio(value: Decimal, base: Decimal) -> str:
    if base and base != 0:
        return format_ratio(value / base)
    return "—"


def _build_profit_loss_table(
    amounts_data: Dict[str, Decimal],
    metrics_data: Dict[str, Decimal],
    cash_data: Dict[str, Decimal],
    unit: str,
) -> List[List[str]]:
    sales = Decimal(amounts_data.get("REV", Decimal("0")))
    cogs = Decimal(amounts_data.get("COGS_TTL", Decimal("0")))
    gross = Decimal(amounts_data.get("GROSS", Decimal("0")))
    opex = Decimal(amounts_data.get("OPEX_TTL", Decimal("0")))
    op = Decimal(amounts_data.get("OP", Decimal("0")))
    ord_income = Decimal(amounts_data.get("ORD", Decimal("0")))
    non_operating_income = sum(
        Decimal(amounts_data.get(code, Decimal("0"))) for code in ("NOI_MISC", "NOI_GRANT", "NOI_OTH")
    )
    non_operating_expense = sum(
        Decimal(amounts_data.get(code, Decimal("0"))) for code in ("NOE_INT", "NOE_OTH")
    )
    net_income = Decimal(cash_data.get("税引後利益", Decimal("0")))
    row_notes = {
        "売上高": "営業収入の総額。",
        "売上原価": "仕入・外注・労務など売上連動の変動費。",
        "粗利": "売上高−売上原価で算出される限界利益。",
        "販管費": "人件費や広告費等の固定費・半固定費。",
        "営業利益": "本業で創出した利益。",
        "営業外収益": "補助金や受取利息など本業以外の収益。",
        "営業外費用": "支払利息等の本業以外の費用。",
        "経常利益": "営業利益＋営業外収支の合計。",
        "税引後利益": "法人税等控除後の最終利益。",
    }
    rows: List[List[str]] = [
        ["項目", "金額", "構成比", "注記"],
        ["売上高", format_amount_with_unit(sales, unit), "100%", row_notes.get("売上高", "")],
        ["売上原価", format_amount_with_unit(cogs, unit), _safe_ratio(cogs, sales), row_notes.get("売上原価", "")],
        ["粗利", format_amount_with_unit(gross, unit), format_ratio(metrics_data.get("gross_margin", Decimal("0"))), row_notes.get("粗利", "")],
        ["販管費", format_amount_with_unit(opex, unit), _safe_ratio(opex, sales), row_notes.get("販管費", "")],
        ["営業利益", format_amount_with_unit(op, unit), format_ratio(metrics_data.get("op_margin", Decimal("0"))), row_notes.get("営業利益", "")],
        ["営業外収益", format_amount_with_unit(non_operating_income, unit), _safe_ratio(non_operating_income, sales), row_notes.get("営業外収益", "")],
        ["営業外費用", format_amount_with_unit(non_operating_expense, unit), _safe_ratio(non_operating_expense, sales), row_notes.get("営業外費用", "")],
        ["経常利益", format_amount_with_unit(ord_income, unit), format_ratio(metrics_data.get("ord_margin", Decimal("0"))), row_notes.get("経常利益", "")],
        ["税引後利益", format_amount_with_unit(net_income, unit), _safe_ratio(net_income, sales), row_notes.get("税引後利益", "")],
    ]
    return rows


def _build_cash_flow_table(cash_data: Dict[str, Decimal], unit: str) -> List[List[str]]:
    notes = {
        "営業キャッシュフロー": "税前利益・減価償却等から算出される本業の稼ぐ力。",
        "投資キャッシュフロー": "設備投資やM&Aなど成長投資に伴うキャッシュ。",
        "財務キャッシュフロー": "借入・返済・配当など財務活動に伴うキャッシュ。",
        "キャッシュ増減": "期首残高との差分。マイナスの場合は資金繰り改善が必要。",
        "減価償却": "キャッシュアウトを伴わない費用で、資金繰り調整時のポイント。",
    }
    return [
        ["区分", "金額", "注記"],
        [
            "営業キャッシュフロー",
            format_amount_with_unit(cash_data.get("営業キャッシュフロー", Decimal("0")), unit),
            notes.get("営業キャッシュフロー", ""),
        ],
        [
            "投資キャッシュフロー",
            format_amount_with_unit(cash_data.get("投資キャッシュフロー", Decimal("0")), unit),
            notes.get("投資キャッシュフロー", ""),
        ],
        [
            "財務キャッシュフロー",
            format_amount_with_unit(cash_data.get("財務キャッシュフロー", Decimal("0")), unit),
            notes.get("財務キャッシュフロー", ""),
        ],
        [
            "キャッシュ増減",
            format_amount_with_unit(cash_data.get("キャッシュ増減", Decimal("0")), unit),
            notes.get("キャッシュ増減", ""),
        ],
        [
            "減価償却",
            format_amount_with_unit(cash_data.get("減価償却", Decimal("0")), unit),
            notes.get("減価償却", ""),
        ],
    ]


def _build_investment_table(bundle, unit: str) -> List[List[str]]:
    rows: List[List[str]] = [["投資名", "金額", "開始月", "耐用年数", "注記"]]
    total = Decimal("0")
    for item in bundle.capex.items:
        amount = Decimal(item.amount)
        total += amount
        annual_depr = getattr(item, "annual_depreciation", None)
        if callable(annual_depr):
            depreciation = annual_depr()
        else:
            life_years = Decimal(getattr(item, "useful_life_years", 1) or 1)
            depreciation = amount / life_years if life_years else Decimal("0")
        rows.append(
            [
                item.name,
                format_amount_with_unit(amount, unit),
                f"{int(item.start_month)}月",
                f"{int(item.useful_life_years)}年",
                f"年額減価償却 {format_amount_with_unit(depreciation, unit)}",
            ]
        )
    rows.append([
        "合計",
        format_amount_with_unit(total, unit),
        "",
        "",
        f"投資件数 {len(bundle.capex.items)}件",
    ])
    return rows


def _create_summary_chart(amounts_data: Dict[str, Decimal]) -> bytes:
    categories = ["売上高", "粗利", "営業利益", "経常利益"]
    values = [
        float(Decimal(amounts_data.get(code, Decimal("0"))))
        for code in ("REV", "GROSS", "OP", "ORD")
    ]
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    bars = ax.barh(categories, values, color=[
        THEME_COLORS["chart_blue"],
        THEME_COLORS["chart_green"],
        THEME_COLORS["chart_orange"],
        THEME_COLORS["chart_purple"],
    ])
    ax.set_xlabel("金額")
    ax.set_xlim(left=0)
    for bar, value in zip(bars, values):
        ax.text(value, bar.get_y() + bar.get_height() / 2, f"¥{value:,.0f}", va='center', ha='left')
    ax.grid(axis='x', linestyle='--', alpha=0.3)
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=220)
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


def _ensure_pdf_font() -> str:
    """Register a Japanese-capable font for ReportLab if needed."""

    try:
        pdfmetrics.getFont(PDF_FONT_NAME)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT_NAME))
    return PDF_FONT_NAME


def _create_pdf_report(
    title: str,
    subtitle: str,
    sections: Sequence[str],
    tables: Dict[str, List[List[str]]],
    *,
    chart_bytes: bytes | None,
    logo_bytes: bytes | None,
    seal_bytes: bytes | None,
    section_meta: Dict[str, ReportSectionMeta] | None = None,
    section_notes: Dict[str, str] | None = None,
    include_notes: bool = False,
) -> bytes:
    font_name = _ensure_pdf_font()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "HeadingJP",
        parent=styles["Heading2"],
        fontName=font_name,
        textColor=colors.HexColor(THEME_COLORS["primary"]),
    )
    title_style = ParagraphStyle(
        "TitleJP",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        leading=22,
    )
    subtitle_style = ParagraphStyle(
        "SubtitleJP",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=11,
        textColor=colors.HexColor(THEME_COLORS["text_subtle"]),
    )
    body_style = ParagraphStyle(
        "BodyJP",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=11,
        leading=16,
    )
    note_style = ParagraphStyle(
        "NoteJP",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor(THEME_COLORS["text_subtle"]),
    )
    meta_lookup = section_meta or {}
    notes_lookup = section_notes or {}
    story: List = []
    if logo_bytes:
        story.append(PlatypusImage(io.BytesIO(logo_bytes), width=140, height=42))
        story.append(Spacer(1, 12))
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(subtitle, subtitle_style))
    story.append(Spacer(1, 18))
    if chart_bytes:
        story.append(PlatypusImage(io.BytesIO(chart_bytes), width=420, height=240))
        story.append(Spacer(1, 18))
    for section in sections:
        table_data = tables.get(section)
        if not table_data:
            continue
        meta = meta_lookup.get(section)
        heading_text = meta.title if meta else section
        story.append(Paragraph(heading_text, heading_style))
        if meta and meta.description:
            story.append(Paragraph(meta.description, note_style))
        story.append(Spacer(1, 6))
        col_count = len(table_data[0]) if table_data else 0
        if col_count == 2:
            col_widths = [220, 180]
        elif col_count == 3:
            col_widths = [160, 120, 120]
        elif col_count == 4:
            col_widths = [150, 120, 90, 130]
        elif col_count == 5:
            col_widths = [140, 110, 80, 80, 130]
        else:
            col_widths = None
        table_component = Table(table_data, colWidths=col_widths)
        table_styles = [
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(THEME_COLORS["surface_alt"])),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(THEME_COLORS["primary"])),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(THEME_COLORS["neutral"])),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor(THEME_COLORS["surface"])],),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        if col_count >= 3:
            table_styles.append(("ALIGN", (col_count - 1, 1), (col_count - 1, -1), "LEFT"))
        table_component.setStyle(TableStyle(table_styles))
        story.append(table_component)
        if include_notes:
            note_text = notes_lookup.get(section)
            if note_text:
                story.append(Spacer(1, 6))
                story.append(Paragraph(f"※{note_text}", note_style))
        story.append(Spacer(1, 16))
    if seal_bytes:
        story.append(Spacer(1, 12))
        story.append(Paragraph("承認", body_style))
        story.append(Spacer(1, 6))
        story.append(PlatypusImage(io.BytesIO(seal_bytes), width=120, height=120))
    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _create_excel_report(
    sections: Sequence[str],
    tables: Dict[str, List[List[str]]],
    *,
    chart_bytes: bytes | None,
    logo_bytes: bytes | None,
    metadata: Dict[str, str],
) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        section_to_sheet = {
            "損益計画": "損益計画",
            "資金繰り表": "資金繰り",
            "投資計画": "投資計画",
        }
        for section in sections:
            table = tables.get(section)
            if not table:
                continue
            df = pd.DataFrame(table[1:], columns=table[0])
            sheet_name = section_to_sheet.get(section, section[:31])
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        meta_df = pd.DataFrame(
            {"項目": list(metadata.keys()), "値": list(metadata.values())}
        )
        meta_df.to_excel(writer, sheet_name="メタ情報", index=False)
        workbook = writer.book
        if logo_bytes and "損益計画" in workbook.sheetnames:
            image = ExcelImage(io.BytesIO(logo_bytes))
            image.width = 200
            image.height = 70
            workbook["損益計画"].add_image(image, "E2")
        if chart_bytes and "損益計画" in workbook.sheetnames:
            chart_image = ExcelImage(io.BytesIO(chart_bytes))
            chart_image.width = 520
            chart_image.height = 320
            workbook["損益計画"].add_image(chart_image, "H2")
    buffer.seek(0)
    return buffer.getvalue()


def _create_word_report(
    title: str,
    subtitle: str,
    sections: Sequence[str],
    tables: Dict[str, List[List[str]]],
    *,
    chart_bytes: bytes | None,
    logo_bytes: bytes | None,
    seal_bytes: bytes | None,
    section_meta: Dict[str, ReportSectionMeta] | None = None,
    section_notes: Dict[str, str] | None = None,
    include_notes: bool = False,
) -> bytes:
    doc = Document()
    meta_lookup = section_meta or {}
    notes_lookup = section_notes or {}
    if logo_bytes:
        doc.add_picture(io.BytesIO(logo_bytes), width=Inches(1.8))
    doc.add_heading(title, level=1)
    doc.add_paragraph(subtitle)
    if chart_bytes:
        doc.add_picture(io.BytesIO(chart_bytes), width=Inches(5.5))
    for section in sections:
        table = tables.get(section)
        if not table:
            continue
        meta = meta_lookup.get(section)
        heading_text = meta.title if meta else section
        doc.add_heading(heading_text, level=2)
        if meta and meta.description:
            doc.add_paragraph(meta.description)
        word_table = doc.add_table(rows=len(table), cols=len(table[0]))
        word_table.style = "Light List Accent 1"
        for row_idx, row in enumerate(table):
            for col_idx, value in enumerate(row):
                word_table.rows[row_idx].cells[col_idx].text = str(value)
        if include_notes:
            note_text = notes_lookup.get(section)
            if note_text:
                doc.add_paragraph(f"※{note_text}")
    if seal_bytes:
        doc.add_paragraph("承認")
        doc.add_picture(io.BytesIO(seal_bytes), width=Inches(1.5))
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _execute_with_spinner(label: str, task: Callable[[], T]) -> T | None:
    """Run a task while showing a spinner and handle failures gracefully."""

    try:
        with st.spinner(f"{label}を生成しています..."):
            return task()
    except Exception:
        st.error(
            f"{label}の生成に失敗しました。入力内容を見直して再度お試しください。"
            f" 解決しない場合は {SUPPORT_CONTACT} までお問い合わせください。"
        )
        return None

default_report_options = {
    "selected_formats": ["PDF", "Excel", "Word"],
    "title": f"経営計画サマリー FY{fiscal_year}",
    "subtitle": f"表示単位: {unit} ｜ FTE: {fte}",
    "include_charts": True,
    "sections": list(REPORT_SECTIONS),
    "include_logo": True,
    "include_seal": False,
    "include_notes": True,
}
report_options = st.session_state.setdefault("report_options", default_report_options.copy())
for key, value in default_report_options.items():
    report_options.setdefault(key, value)

with st.form("report_options_form"):
    st.markdown("### レポート設定")
    selected_formats = st.multiselect(
        "出力フォーマット",
        ["PDF", "Excel", "Word"],
        default=report_options.get("selected_formats", ["PDF", "Excel", "Word"]),
    )
    title_input = st.text_input(
        "レポートタイトル",
        value=report_options.get("title", default_report_options["title"]),
    )
    subtitle_input = st.text_input(
        "サブタイトル",
        value=report_options.get("subtitle", default_report_options["subtitle"]),
    )
    selected_sections = st.multiselect(
        "含めるセクション",
        list(REPORT_SECTIONS),
        default=report_options.get("sections", list(REPORT_SECTIONS)),
        format_func=lambda key: REPORT_SECTION_LOOKUP.get(key, ReportSectionMeta(key, key, "")).title,
    )
    for section_key in selected_sections:
        meta = REPORT_SECTION_LOOKUP.get(section_key)
        if meta and meta.description:
            st.caption(f"・{meta.title} — {meta.description}")
    include_charts = st.checkbox(
        "KPIハイライトの図表を含める",
        value=report_options.get("include_charts", True),
    )
    include_logo = st.checkbox(
        "ヘッダーに企業ロゴを表示",
        value=report_options.get("include_logo", True),
    )
    include_seal = st.checkbox(
        "印影画像を挿入する",
        value=report_options.get("include_seal", False),
    )
    include_notes = st.toggle(
        "金融機関向け注記を併記する",
        value=report_options.get("include_notes", True),
        help="損益計画・資金繰り表・投資計画の表に注釈と補足を含めます。",
    )
    submitted = st.form_submit_button("設定を更新", type="primary")
    if submitted:
        report_options.update(
            {
                "selected_formats": selected_formats or ["PDF"],
                "title": title_input.strip() or default_report_options["title"],
                "subtitle": subtitle_input.strip() or default_report_options["subtitle"],
                "sections": selected_sections or list(REPORT_SECTIONS),
                "include_charts": include_charts,
                "include_logo": include_logo,
                "include_seal": include_seal,
                "include_notes": include_notes,
            }
        )
        st.session_state["report_options"] = report_options
        st.success("レポート設定を更新しました。", icon="✔")

logo_upload = st.file_uploader("企業ロゴ (PNG/JPG/SVG)", type=["png", "jpg", "jpeg", "svg"], key="report_logo_upload")
if logo_upload is not None:
    st.session_state["report_logo_bytes"] = logo_upload.getvalue()
    st.session_state["report_logo_name"] = logo_upload.name
    st.toast("ロゴを読み込みました。", icon="図")

seal_upload = st.file_uploader("印影画像 (PNG/JPG)", type=["png", "jpg", "jpeg"], key="report_seal_upload")
if seal_upload is not None:
    st.session_state["report_seal_bytes"] = seal_upload.getvalue()
    st.session_state["report_seal_name"] = seal_upload.name
    st.toast("印影を読み込みました。", icon="印")

logo_bytes = (
    st.session_state.get("report_logo_bytes") if report_options.get("include_logo", True) else None
)
seal_bytes = (
    st.session_state.get("report_seal_bytes") if report_options.get("include_seal", False) else None
)

if logo_bytes:
    st.image(logo_bytes, width=160, caption="ヘッダーロゴ プレビュー")
if seal_bytes:
    st.image(seal_bytes, width=120, caption="印影プレビュー")

selected_sections = [section for section in report_options.get("sections", REPORT_SECTIONS) if section in REPORT_SECTIONS]
if not selected_sections:
    selected_sections = list(REPORT_SECTIONS)

include_notes_flag = bool(report_options.get("include_notes", True))
section_notes = {key: meta.note for key, meta in REPORT_SECTION_LOOKUP.items() if meta.note}

tables = {
    "損益計画": _build_profit_loss_table(amounts, metrics, cash_flow_data, unit),
    "資金繰り表": _build_cash_flow_table(cash_flow_data, unit),
    "投資計画": _build_investment_table(bundle, unit),
}
chart_bytes = _create_summary_chart(amounts) if report_options.get("include_charts", True) else None
metadata = {
    "作成日時": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    "会計年度": f"FY{fiscal_year}",
    "表示単位": unit,
    "FTE": str(fte),
    "注記付与": "あり" if include_notes_flag else "なし",
}

if include_notes_flag:
    st.caption("注記付きフォーマットで金融機関提出資料に対応します。")
else:
    st.caption("注記なしのシンプルフォーマットで出力します。")

pdf_tab, excel_tab, word_tab = st.tabs(["PDF", "Excel", "Word"])

with pdf_tab:
    st.subheader("PDFレポート")
    if "PDF" not in report_options.get("selected_formats", []):
        st.info("PDF出力はオフになっています。")
    else:
        pdf_bytes = _execute_with_spinner(
            "PDFレポート",
            lambda: _create_pdf_report(
                report_options.get("title", default_report_options["title"]),
                report_options.get("subtitle", default_report_options["subtitle"]),
                selected_sections,
                tables,
                chart_bytes=chart_bytes,
                logo_bytes=logo_bytes,
                seal_bytes=seal_bytes,
                section_meta=REPORT_SECTION_LOOKUP,
                section_notes=section_notes if include_notes_flag else None,
                include_notes=include_notes_flag,
            ),
        )
        if pdf_bytes is not None:
            st.download_button(
                "［PDF］ダウンロード",
                data=pdf_bytes,
                file_name=f"plan_report_{fiscal_year}.pdf",
                mime="application/pdf",
                **use_container_width_kwargs(st.download_button),
            )

with excel_tab:
    st.subheader("Excelレポート")
    if "Excel" not in report_options.get("selected_formats", []):
        st.info("Excel出力はオフになっています。")
    else:
        excel_bytes = _execute_with_spinner(
            "Excelレポート",
            lambda: _create_excel_report(
                selected_sections,
                tables,
                chart_bytes=chart_bytes,
                logo_bytes=logo_bytes,
                metadata=metadata,
            ),
        )
        if excel_bytes is not None:
            st.download_button(
                "［Excel］ダウンロード",
                data=excel_bytes,
                file_name=f"plan_report_{fiscal_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                **use_container_width_kwargs(st.download_button),
            )

with word_tab:
    st.subheader("Wordレポート")
    if "Word" not in report_options.get("selected_formats", []):
        st.info("Word出力はオフになっています。")
    else:
        word_bytes = _execute_with_spinner(
            "Wordレポート",
            lambda: _create_word_report(
                report_options.get("title", default_report_options["title"]),
                report_options.get("subtitle", default_report_options["subtitle"]),
                selected_sections,
                tables,
                chart_bytes=chart_bytes,
                logo_bytes=logo_bytes,
                seal_bytes=seal_bytes,
                section_meta=REPORT_SECTION_LOOKUP,
                section_notes=section_notes if include_notes_flag else None,
                include_notes=include_notes_flag,
            ),
        )
        if word_bytes is not None:
            st.download_button(
                "［Word］ダウンロード",
                data=word_bytes,
                file_name=f"plan_report_{fiscal_year}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                **use_container_width_kwargs(st.download_button),
            )
