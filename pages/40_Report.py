"""Report export page for PDF / Excel / Word outputs."""
from __future__ import annotations

import io
from decimal import Decimal
from typing import Callable, Dict, TypeVar

import pandas as pd
import streamlit as st
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from ui.streamlit_compat import use_container_width_kwargs

from calc import compute, plan_from_models, summarize_plan_metrics
from formatting import format_amount_with_unit, format_ratio
from state import ensure_session_defaults, load_finance_bundle
from theme import inject_theme

st.set_page_config(
    page_title="経営計画スタジオ｜Report",
    page_icon="📝",
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

st.title("📝 レポート出力")
st.caption("主要指標とKPIのサマリーをPDF / Excel / Word形式でダウンロードできます。")

SUPPORT_CONTACT = "support@keieiplan.jp"
PDF_FONT_NAME = "HeiseiKakuGo-W5"
T = TypeVar("T")


def _ensure_pdf_font() -> str:
    """Register a Japanese-capable font for ReportLab if needed."""

    try:
        pdfmetrics.getFont(PDF_FONT_NAME)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT_NAME))
    return PDF_FONT_NAME


def _create_pdf_report(summary_lines: list[str]) -> bytes:
    font_name = _ensure_pdf_font()
    buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    text_object = pdf_canvas.beginText(40, height - 60)
    text_object.setFont(font_name, 14)
    text_object.setLeading(20)
    text_object.textLine("経営計画スタジオ｜サマリーレポート")
    text_object.setFont(font_name, 11)
    text_object.setLeading(16)
    text_object.textLine("")
    for line in summary_lines:
        wrapped_lines = simpleSplit(line, font_name, 11, width - 80)
        for wrapped in wrapped_lines:
            text_object.textLine(wrapped)
        text_object.textLine("")
    pdf_canvas.drawText(text_object)
    pdf_canvas.showPage()
    pdf_canvas.save()
    buffer.seek(0)
    return buffer.getvalue()


def _create_excel_report(amounts: Dict[str, Decimal], metrics: Dict[str, Decimal]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "項目": ["売上高", "粗利", "営業利益", "経常利益"],
                "金額": [
                    float(amounts.get("REV", Decimal("0"))),
                    float(amounts.get("GROSS", Decimal("0"))),
                    float(amounts.get("OP", Decimal("0"))),
                    float(amounts.get("ORD", Decimal("0"))),
                ],
            }
        ).to_excel(writer, sheet_name="PL", index=False)

        pd.DataFrame(
            {
                "指標": ["粗利率", "営業利益率", "経常利益率", "損益分岐点"],
                "値": [
                    float(metrics.get("gross_margin", Decimal("0"))),
                    float(metrics.get("op_margin", Decimal("0"))),
                    float(metrics.get("ord_margin", Decimal("0"))),
                    float(metrics.get("breakeven", Decimal("0"))),
                ],
            }
        ).to_excel(writer, sheet_name="KPI", index=False)

    buffer.seek(0)
    return buffer.getvalue()


def _create_word_report(
    summary_lines: list[str], fiscal_year: int, unit: str, fte: Decimal
) -> bytes:
    doc = Document()
    doc.add_heading("経営計画スタジオ レポート", level=1)
    doc.add_paragraph(f"FY{fiscal_year} / 表示単位: {unit} / FTE: {fte}")
    doc.add_paragraph("主要KPI")
    if len(summary_lines) > 1:
        first_item = doc.add_paragraph()
        first_item.style = "List Bullet"
        first_item.add_run(summary_lines[1])
        for line in summary_lines[2:]:
            para = doc.add_paragraph()
            para.style = "List Bullet"
            para.add_run(line)
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

pdf_tab, excel_tab, word_tab = st.tabs(["PDF", "Excel", "Word"])

pdf_summary = [
    f"FY{fiscal_year} 計画サマリー",
    f"売上高: {format_amount_with_unit(amounts.get('REV', Decimal('0')), unit)}",
    f"粗利率: {format_ratio(metrics.get('gross_margin'))}",
    f"経常利益: {format_amount_with_unit(amounts.get('ORD', Decimal('0')), unit)}",
    f"経常利益率: {format_ratio(metrics.get('ord_margin'))}",
    f"損益分岐点売上高: {format_amount_with_unit(metrics.get('breakeven', Decimal('0')), unit)}",
]

with pdf_tab:
    st.subheader("PDFレポート")
    pdf_bytes = _execute_with_spinner("PDFレポート", lambda: _create_pdf_report(pdf_summary))
    if pdf_bytes is not None:
        st.download_button(
            "📄 PDFダウンロード",
            data=pdf_bytes,
            file_name=f"plan_report_{fiscal_year}.pdf",
            mime="application/pdf",
            **use_container_width_kwargs(st.download_button),
        )

with excel_tab:
    st.subheader("Excelレポート")
    excel_bytes = _execute_with_spinner(
        "Excelレポート", lambda: _create_excel_report(amounts, metrics)
    )
    if excel_bytes is not None:
        st.download_button(
            "📊 Excelダウンロード",
            data=excel_bytes,
            file_name=f"plan_report_{fiscal_year}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            **use_container_width_kwargs(st.download_button),
        )

with word_tab:
    st.subheader("Wordレポート")
    word_bytes = _execute_with_spinner(
        "Wordレポート",
        lambda: _create_word_report(pdf_summary, fiscal_year, unit, fte),
    )
    if word_bytes is not None:
        st.download_button(
            "📝 Wordダウンロード",
            data=word_bytes,
            file_name=f"plan_report_{fiscal_year}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            **use_container_width_kwargs(st.download_button),
        )
