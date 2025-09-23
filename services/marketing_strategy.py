"""Utility functions for marketing strategy (4P/3C/UVP/STP) suggestions."""

from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Dict, Iterable, List, Mapping, Sequence

SESSION_STATE_KEY = "marketing_strategy"

FOUR_P_KEYS: Sequence[str] = ("product", "price", "place", "promotion")
FOUR_P_LABELS: Mapping[str, str] = {
    "product": "製品 (Product)",
    "price": "価格 (Price)",
    "place": "流通チャネル (Place)",
    "promotion": "プロモーション (Promotion)",
}

DEFAULT_MARKETING_STATE: Mapping[str, object] = {
    "four_p": {
        key: {"current": "", "challenge": "", "metric": "", "price_point": 0.0}
        if key == "price"
        else {"current": "", "challenge": "", "metric": ""}
        for key in FOUR_P_KEYS
    },
    "customer": {
        "market_size": 0.0,
        "growth_rate": 0.0,
        "needs": "",
        "segments": "",
        "persona": "",
    },
    "company": {
        "strengths": "",
        "weaknesses": "",
        "resources": "",
        "service_score": 3.0,
    },
    "competitor": {
        "top": {
            "name": "",
            "strengths": "",
            "weaknesses": "",
            "price": 0.0,
            "service_score": 3.0,
            "differentiators": "",
        },
        "local": {
            "name": "",
            "strengths": "",
            "weaknesses": "",
            "price": 0.0,
            "service_score": 3.0,
            "differentiators": "",
        },
    },
}

__all__ = [
    "DEFAULT_MARKETING_STATE",
    "FOUR_P_KEYS",
    "FOUR_P_LABELS",
    "SESSION_STATE_KEY",
    "empty_marketing_state",
    "marketing_state_has_content",
    "generate_marketing_recommendations",
]


def empty_marketing_state() -> Dict[str, object]:
    """Return a deep copy of the default marketing strategy state."""

    return deepcopy(DEFAULT_MARKETING_STATE)


def marketing_state_has_content(state: Mapping[str, object] | None) -> bool:
    """Return True if the marketing state contains any user-provided information."""

    if not isinstance(state, Mapping):
        return False

    four_p = state.get("four_p")
    if isinstance(four_p, Mapping):
        for key in FOUR_P_KEYS:
            entry = four_p.get(key)
            if not isinstance(entry, Mapping):
                continue
            for field in ("current", "challenge", "metric"):
                if str(entry.get(field, "")).strip():
                    return True
            if key == "price":
                price = _safe_float(entry.get("price_point"))
                if price and price > 0:
                    return True

    customer = state.get("customer")
    if isinstance(customer, Mapping):
        for field in ("needs", "segments", "persona"):
            if str(customer.get(field, "")).strip():
                return True
        for field in ("market_size", "growth_rate"):
            number = _safe_float(customer.get(field))
            if number and abs(number) > 0:
                return True

    company = state.get("company")
    if isinstance(company, Mapping):
        for field in ("strengths", "weaknesses", "resources"):
            if str(company.get(field, "")).strip():
                return True
        service_score = _safe_float(company.get("service_score"))
        if service_score is not None and abs(service_score - 3.0) > 1e-6:
            return True

    competitor = state.get("competitor")
    if isinstance(competitor, Mapping):
        for segment in ("top", "local"):
            record = competitor.get(segment)
            if not isinstance(record, Mapping):
                continue
            for field in ("name", "strengths", "weaknesses", "differentiators"):
                if str(record.get(field, "")).strip():
                    return True
            price = _safe_float(record.get("price"))
            if price and price > 0:
                return True
            service = _safe_float(record.get("service_score"))
            if service is not None and abs(service - 3.0) > 1e-6:
                return True

    return False


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _format_currency(value: float | None) -> str:
    if value is None:
        return "-"
    return f"¥{value:,.0f}"


def _format_score(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}"


def _format_percentage(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def _format_market_size(value: float | None) -> str:
    if value is None:
        return "未入力"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}十億規模"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}百万規模"
    if value >= 1_000:
        return f"{value:,.0f}規模"
    if value > 0:
        return f"約{value:,.0f}"
    return "未入力"


def _price_gap(base: float | None, reference: float | None) -> tuple[float, float] | None:
    if base is None or reference is None or reference == 0:
        return None
    diff = base - reference
    percent = diff / reference * 100
    return diff, percent


def _service_gap(base: float | None, reference: float | None) -> float | None:
    if base is None or reference is None:
        return None
    return base - reference


def _combine_unique(lines: Iterable[str]) -> List[str]:
    unique: Dict[str, None] = {}
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text not in unique:
            unique[text] = None
    return list(unique.keys())


def _metric_hint(metric_text: str) -> str | None:
    if not metric_text:
        return None
    digits = re.findall(r"-?\d+(?:\.\d+)?", metric_text)
    if not digits:
        return metric_text
    value = digits[0]
    if "%" in metric_text:
        return f"目標値 {value}% で進捗をモニタリング"
    return f"目標値 {value} で進捗をモニタリング"


def generate_four_p_suggestions(
    *,
    four_p: Mapping[str, Mapping[str, object]],
    customer: Mapping[str, object],
    company: Mapping[str, object],
    competitor: Mapping[str, Mapping[str, object]],
    business_context: Mapping[str, object] | None = None,
) -> Dict[str, List[str]]:
    context = business_context or {}
    needs = _clean_text(customer.get("needs")) or _clean_text(context.get("three_c_customer"))
    segments = _clean_text(customer.get("segments")) or _clean_text(context.get("bmc_customer_segments"))
    persona = _clean_text(customer.get("persona"))
    strengths = _clean_text(company.get("strengths")) or _clean_text(context.get("three_c_company"))
    resources = _clean_text(company.get("resources"))
    company_service = _safe_float(company.get("service_score"))

    top_comp = competitor.get("top", {}) if isinstance(competitor.get("top"), Mapping) else {}
    local_comp = competitor.get("local", {}) if isinstance(competitor.get("local"), Mapping) else {}
    top_price = _safe_float(top_comp.get("price"))
    top_service = _safe_float(top_comp.get("service_score"))
    local_price = _safe_float(local_comp.get("price"))
    local_service = _safe_float(local_comp.get("service_score"))

    suggestions: Dict[str, List[str]] = {}

    for key in FOUR_P_KEYS:
        entry = four_p.get(key, {}) if isinstance(four_p.get(key), Mapping) else {}
        current = _clean_text(entry.get("current"))
        challenge = _clean_text(entry.get("challenge"))
        metric = _clean_text(entry.get("metric"))
        metric_hint = _metric_hint(metric) if metric else None

        lines: List[str] = []

        if key == "product":
            if needs and strengths:
                lines.append(
                    f"顧客ニーズ「{needs}」と自社の強み「{strengths}」を掛け合わせ、{current or '主力製品'}の価値訴求を磨き込みましょう。"
                )
            elif needs:
                lines.append(f"顧客ニーズ「{needs}」を優先課題として、機能ロードマップを整理しましょう。")
            elif strengths:
                lines.append(f"自社の強み「{strengths}」を前面に出す製品メッセージを整備しましょう。")

            if persona or segments:
                audience = persona or segments
                lines.append(
                    f"{audience}向けのオンボーディング体験と活用シナリオを用意し、継続利用率を高めます。"
                )

            if challenge:
                lines.append(f"課題『{challenge}』の改善仮説をユーザーテストで素早く検証しましょう。")

        elif key == "price":
            our_price = _safe_float(entry.get("price_point"))
            if our_price is not None and our_price > 0:
                if top_price:
                    gap = _price_gap(our_price, top_price)
                    if gap:
                        diff, percent = gap
                        if diff < 0:
                            lines.append(
                                f"業界トップより{abs(diff):,.0f}円（{abs(percent):.1f}%）低い価格優位を活かし、価値訴求とセットで提示しましょう。"
                            )
                        elif diff > 0:
                            service_gap = _service_gap(company_service, top_service)
                            if service_gap and service_gap > 0:
                                lines.append(
                                    f"業界トップより{diff:,.0f}円（{percent:.1f}%）高い価格設定なので、サポート品質で{service_gap:.1f}ポイント上回る点を強調しましょう。"
                                )
                            else:
                                lines.append(
                                    f"業界トップより{diff:,.0f}円（{percent:.1f}%）高いため、プレミアム要素や導入成果を具体的な事例で示しましょう。"
                                )
                if local_price:
                    gap = _price_gap(our_price, local_price)
                    if gap:
                        diff, percent = gap
                        if diff < 0:
                            lines.append(
                                f"地元競合比で{abs(diff):,.0f}円（{abs(percent):.1f}%）お得なプランを提示できるため、乗り換え施策に活用できます。"
                            )
                        elif diff > 0:
                            lines.append(
                                f"地元競合より{diff:,.0f}円（{percent:.1f}%）高い場合は、地域密着の価値提案と合わせて納得感を高めましょう。"
                            )
            if challenge:
                lines.append(f"課題『{challenge}』に対し、コスト構造と値引き条件を整理し価格シナリオを検証します。")

            if metric_hint:
                lines.append(metric_hint)

        elif key == "place":
            if segments:
                lines.append(
                    f"主要セグメント「{segments}」が利用するチャネルに合わせ、{current or 'チャネル戦略'}を再設計しましょう。"
                )
            if persona:
                lines.append(
                    f"ペルソナ「{persona}」の購買導線を分解し、オンラインとオフラインの接点を統合します。"
                )
            if resources:
                lines.append(f"活用できるリソース「{resources}」を基に営業・流通体制を最適化します。")
            if challenge:
                lines.append(f"課題『{challenge}』を改善するため、チャネル別のCVRや在庫回転を可視化しましょう。")
            if metric_hint:
                lines.append(metric_hint)

        elif key == "promotion":
            if persona or segments:
                audience = persona or segments
                lines.append(
                    f"{audience}向けの訴求メッセージを作成し、タッチポイントごとにCTAを明確化します。"
                )
            if needs:
                lines.append(f"ニーズ「{needs}」をキーワードにコンテンツや広告を設計し、認知から比較検討まで一貫させましょう。")
            if company_service and top_service:
                gap = _service_gap(company_service, top_service)
                if gap and gap > 0:
                    lines.append(
                        f"サポート品質で業界トップに対し{gap:.1f}ポイント優位な点を、導入事例や指標で伝えましょう。"
                    )
            if challenge:
                lines.append(f"課題『{challenge}』は、テストキャンペーンとファネル分析で検証しましょう。")
            if metric_hint:
                lines.append(metric_hint)

        suggestions[key] = _combine_unique(lines)

    return suggestions


def _build_price_positioning(
    our_price: float | None,
    top_price: float | None,
    local_price: float | None,
) -> str:
    fragments: List[str] = []
    if our_price is None or our_price <= 0:
        return ""

    if top_price:
        gap = _price_gap(our_price, top_price)
        if gap:
            diff, percent = gap
            if diff < 0:
                fragments.append(
                    f"業界トップ比 {abs(diff):,.0f}円（{abs(percent):.1f}%）低価格"
                )
            elif diff > 0:
                fragments.append(
                    f"業界トップ比 +{diff:,.0f}円（+{percent:.1f}%）のプレミアム価格"
                )

    if local_price:
        gap = _price_gap(our_price, local_price)
        if gap:
            diff, percent = gap
            if diff < 0:
                fragments.append(
                    f"地元競合比 {abs(diff):,.0f}円（{abs(percent):.1f}%）低価格"
                )
            elif diff > 0:
                fragments.append(
                    f"地元競合比 +{diff:,.0f}円（+{percent:.1f}%）"
                )

    return "、".join(fragments)


def _build_service_positioning(
    our_score: float | None,
    top_score: float | None,
    local_score: float | None,
) -> str:
    fragments: List[str] = []
    if our_score is None:
        return ""

    if top_score:
        gap = _service_gap(our_score, top_score)
        if gap and gap > 0:
            fragments.append(f"業界トップ比 +{gap:.1f}ポイントのサポート品質")
        elif gap and gap < 0:
            fragments.append(f"業界トップ比 {gap:.1f}ポイント劣後")

    if local_score:
        gap = _service_gap(our_score, local_score)
        if gap and gap > 0:
            fragments.append(f"地元競合比 +{gap:.1f}ポイントの体験価値")
        elif gap and gap < 0:
            fragments.append(f"地元競合比 {gap:.1f}ポイント劣後")

    return "、".join(fragments)


def generate_uvp_stp_suggestions(
    *,
    four_p: Mapping[str, Mapping[str, object]],
    customer: Mapping[str, object],
    company: Mapping[str, object],
    competitor: Mapping[str, Mapping[str, object]],
    business_context: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    context = business_context or {}
    segments = _clean_text(customer.get("segments")) or _clean_text(context.get("bmc_customer_segments"))
    persona = _clean_text(customer.get("persona"))
    needs = _clean_text(customer.get("needs")) or _clean_text(context.get("three_c_customer"))
    strengths = _clean_text(company.get("strengths")) or _clean_text(context.get("bmc_value_proposition"))
    weaknesses = _clean_text(company.get("weaknesses"))
    resources = _clean_text(company.get("resources"))

    market_size = _safe_float(customer.get("market_size"))
    growth_rate = _safe_float(customer.get("growth_rate"))
    company_service = _safe_float(company.get("service_score"))

    top_comp = competitor.get("top", {}) if isinstance(competitor.get("top"), Mapping) else {}
    local_comp = competitor.get("local", {}) if isinstance(competitor.get("local"), Mapping) else {}
    top_name = _clean_text(top_comp.get("name"))
    local_name = _clean_text(local_comp.get("name"))
    top_price = _safe_float(top_comp.get("price"))
    local_price = _safe_float(local_comp.get("price"))
    top_service = _safe_float(top_comp.get("service_score"))
    local_service = _safe_float(local_comp.get("service_score"))

    our_price = _safe_float(four_p.get("price", {}).get("price_point"))

    price_positioning = _build_price_positioning(our_price, top_price, local_price)
    service_positioning = _build_service_positioning(company_service, top_service, local_service)

    target_label = persona or segments or "主要顧客"
    need_label = needs or "課題"
    strength_label = strengths or "自社の独自ノウハウ"

    uvp_parts: List[str] = [f"{target_label}が抱える「{need_label}」を"]
    uvp_parts.append(f"{strength_label}で解決し")
    if service_positioning:
        uvp_parts.append(service_positioning)
    if price_positioning:
        uvp_parts.append(price_positioning)
    uvp_text = "、".join([part for part in uvp_parts if part]) + "ことを約束します。"

    segmentation_text = "市場規模" + _format_market_size(market_size)
    if growth_rate is not None:
        segmentation_text += f"、年成長率 {_format_percentage(growth_rate)}"
    if segments:
        segmentation_text += f"。主要セグメントは「{segments}」。"
    else:
        segmentation_text += "。"

    targeting_text = f"最優先ターゲットは{target_label}。"
    if price_positioning:
        targeting_text += f"価格ポジションは{price_positioning}。"
    if resources:
        targeting_text += f"保有リソース「{resources}」を活用し、受注リード獲得を強化します。"

    positioning_text = "市場での立ち位置を明確化するため、"
    bullets: List[str] = []
    if top_name:
        comparison = []
        if top_price:
            comparison.append(f"価格 { _format_currency(top_price) }")
        if top_service:
            comparison.append(f"サービススコア { _format_score(top_service) }")
        bullets.append(f"{top_name}：" + "、".join(comparison or ["データ未入力"]))
    if local_name:
        comparison = []
        if local_price:
            comparison.append(f"価格 { _format_currency(local_price) }")
        if local_service:
            comparison.append(f"サービススコア { _format_score(local_service) }")
        bullets.append(f"{local_name}：" + "、".join(comparison or ["データ未入力"]))
    if price_positioning or service_positioning:
        bullets.append("自社：" + "、".join(filter(None, [price_positioning, service_positioning])) or "自社：データ未入力")
    if weaknesses:
        bullets.append(f"留意点：弱み「{weaknesses}」を改善する施策を併走")

    if bullets:
        positioning_text += "競合比較の観点では以下を強調します。"
    else:
        positioning_text += "競合比較情報が不足しています。"

    return {
        "uvp": uvp_text,
        "segmentation": segmentation_text,
        "targeting": targeting_text,
        "positioning": positioning_text,
        "positioning_points": bullets,
    }


def build_competitor_table(
    *,
    four_p: Mapping[str, Mapping[str, object]],
    company: Mapping[str, object],
    competitor: Mapping[str, Mapping[str, object]],
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    our_price = _safe_float(four_p.get("price", {}).get("price_point"))
    our_service = _safe_float(company.get("service_score"))

    top_comp = competitor.get("top", {}) if isinstance(competitor.get("top"), Mapping) else {}
    local_comp = competitor.get("local", {}) if isinstance(competitor.get("local"), Mapping) else {}

    rows.append(
        {
            "項目": "主要価格帯 (円)",
            "自社": _format_currency(our_price),
            "業界トップ": _format_currency(_safe_float(top_comp.get("price"))),
            "地元企業": _format_currency(_safe_float(local_comp.get("price"))),
        }
    )

    rows.append(
        {
            "項目": "サービス差別化スコア (1-5)",
            "自社": _format_score(our_service),
            "業界トップ": _format_score(_safe_float(top_comp.get("service_score"))),
            "地元企業": _format_score(_safe_float(local_comp.get("service_score"))),
        }
    )

    rows.append(
        {
            "項目": "強み",
            "自社": _clean_text(company.get("strengths")) or "-",
            "業界トップ": _clean_text(top_comp.get("strengths")) or "-",
            "地元企業": _clean_text(local_comp.get("strengths")) or "-",
        }
    )

    rows.append(
        {
            "項目": "弱み・課題",
            "自社": _clean_text(company.get("weaknesses")) or "-",
            "業界トップ": _clean_text(top_comp.get("weaknesses")) or "-",
            "地元企業": _clean_text(local_comp.get("weaknesses")) or "-",
        }
    )

    rows.append(
        {
            "項目": "差別化ポイント",
            "自社": _clean_text(company.get("resources")) or "-",
            "業界トップ": _clean_text(top_comp.get("differentiators")) or "-",
            "地元企業": _clean_text(local_comp.get("differentiators")) or "-",
        }
    )

    return rows


def build_competitor_highlights(
    *,
    four_p: Mapping[str, Mapping[str, object]],
    company: Mapping[str, object],
    competitor: Mapping[str, Mapping[str, object]],
) -> List[str]:
    lines: List[str] = []
    our_price = _safe_float(four_p.get("price", {}).get("price_point"))
    our_service = _safe_float(company.get("service_score"))

    top_comp = competitor.get("top", {}) if isinstance(competitor.get("top"), Mapping) else {}
    local_comp = competitor.get("local", {}) if isinstance(competitor.get("local"), Mapping) else {}

    top_name = _clean_text(top_comp.get("name")) or "業界トップ"
    local_name = _clean_text(local_comp.get("name")) or "地元競合"

    top_gap = _price_gap(our_price, _safe_float(top_comp.get("price"))) if our_price else None
    local_gap = _price_gap(our_price, _safe_float(local_comp.get("price"))) if our_price else None

    if top_gap:
        diff, percent = top_gap
        comparison = "低い" if diff < 0 else "高い"
        lines.append(
            f"{top_name}と比較して{abs(diff):,.0f}円（{abs(percent):.1f}%）{comparison}価格。"
        )

    if local_gap:
        diff, percent = local_gap
        comparison = "低い" if diff < 0 else "高い"
        lines.append(
            f"{local_name}と比較して{abs(diff):,.0f}円（{abs(percent):.1f}%）{comparison}価格。"
        )

    if our_service is not None:
        top_service = _safe_float(top_comp.get("service_score"))
        local_service = _safe_float(local_comp.get("service_score"))
        if top_service is not None:
            gap = _service_gap(our_service, top_service)
            if gap:
                relation = "高い" if gap > 0 else "低い"
                lines.append(
                    f"サポートスコアは{top_name}比で{abs(gap):.1f}ポイント{relation}水準です。"
                )
        if local_service is not None:
            gap = _service_gap(our_service, local_service)
            if gap:
                relation = "高い" if gap > 0 else "低い"
                lines.append(
                    f"サポートスコアは{local_name}比で{abs(gap):.1f}ポイント{relation}水準です。"
                )

    return _combine_unique(lines)


def generate_marketing_recommendations(
    marketing_state: Mapping[str, object] | None,
    business_context: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    state = marketing_state if isinstance(marketing_state, Mapping) else {}
    four_p = state.get("four_p") if isinstance(state.get("four_p"), Mapping) else {}
    customer = state.get("customer") if isinstance(state.get("customer"), Mapping) else {}
    company = state.get("company") if isinstance(state.get("company"), Mapping) else {}
    competitor = state.get("competitor") if isinstance(state.get("competitor"), Mapping) else {}

    four_p_suggestions = generate_four_p_suggestions(
        four_p=four_p,
        customer=customer,
        company=company,
        competitor=competitor,
        business_context=business_context,
    )

    uvp_stp = generate_uvp_stp_suggestions(
        four_p=four_p,
        customer=customer,
        company=company,
        competitor=competitor,
        business_context=business_context,
    )

    competitor_table = build_competitor_table(
        four_p=four_p,
        company=company,
        competitor=competitor,
    )

    competitor_highlights = build_competitor_highlights(
        four_p=four_p,
        company=company,
        competitor=competitor,
    )

    return {
        "four_p": four_p_suggestions,
        "uvp": uvp_stp.get("uvp", ""),
        "segmentation": uvp_stp.get("segmentation", ""),
        "targeting": uvp_stp.get("targeting", ""),
        "positioning": uvp_stp.get("positioning", ""),
        "positioning_points": uvp_stp.get("positioning_points", []),
        "competitor_table": competitor_table,
        "competitor_highlights": competitor_highlights,
    }

