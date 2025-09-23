"""Tests for marketing strategy recommendation utilities."""

from services.marketing_strategy import (
    empty_marketing_state,
    generate_marketing_recommendations,
    marketing_state_has_content,
)


def test_generate_marketing_recommendations_produces_price_and_service_insights() -> None:
    state = empty_marketing_state()

    # Populate 4P inputs
    state["four_p"]["product"]["current"] = "AI在庫最適化プラットフォーム"
    state["four_p"]["product"]["challenge"] = "導入時の学習期間が長い"
    state["four_p"]["product"]["metric"] = "解約率5%以下"
    state["four_p"]["price"]["price_point"] = 12000.0
    state["four_p"]["price"]["challenge"] = "値引き依存を解消したい"
    state["four_p"]["promotion"]["current"] = "ウェビナーと展示会を併用"

    # 3C inputs
    state["customer"]["needs"] = "在庫過多と欠品を同時に抑制したい"
    state["customer"]["segments"] = "年商5〜10億円の製造業"
    state["customer"]["persona"] = "生産管理マネージャー"
    state["company"]["strengths"] = "導入オンボーディング専門チーム"
    state["company"]["resources"] = "全国対応可能なサポート網"
    state["company"]["service_score"] = 4.5
    state["company"]["weaknesses"] = "マーケティング人員が不足"

    state["competitor"]["top"].update(
        {
            "name": "トップ社",
            "price": 15000.0,
            "service_score": 3.6,
            "strengths": "豊富な導入実績",
        }
    )
    state["competitor"]["local"].update(
        {
            "name": "ローカル社",
            "price": 9000.0,
            "service_score": 3.0,
            "strengths": "地域密着サポート",
        }
    )

    recommendations = generate_marketing_recommendations(state, {"bmc_value_proposition": "初期設定を伴走支援"})

    price_suggestions = recommendations["four_p"]["price"]
    assert any("業界トップより3,000円" in line for line in price_suggestions)
    assert any("地元競合" in line for line in price_suggestions)

    # UVP/STP should not be empty strings
    assert recommendations["uvp"]
    assert recommendations["segmentation"].startswith("市場規模")
    assert recommendations["targeting"].startswith("最優先ターゲット")

    table = recommendations["competitor_table"]
    assert table[0]["自社"] == "¥12,000"
    assert table[1]["自社"] == "4.5"

    highlights = recommendations["competitor_highlights"]
    assert any("トップ社" in item for item in highlights)
    assert any("ローカル社" in item for item in highlights)

    assert marketing_state_has_content(state)
    assert not marketing_state_has_content(empty_marketing_state())
