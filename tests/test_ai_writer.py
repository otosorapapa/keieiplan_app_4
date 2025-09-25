import pytest

from services.ai_writer import BusinessContextGenerator, GenerationError


def test_generate_business_context_for_manufacturing():
    generator = BusinessContextGenerator()
    suggestion = generator.generate_business_context(
        industry="製造業向けSaaS",
        business_model="サブスクリプション",
        target_customer="年商50億円の金属加工メーカー",
        product="IoT連携型生産管理クラウド",
        keywords="サプライチェーンDX, 伴走支援",
        tone="formal",
    )

    fields = suggestion.fields
    assert "金属加工メーカー" in fields["three_c_customer"]
    assert "IoT連携型生産管理クラウド" in fields["bmc_value_proposition"]
    assert suggestion.profile_name == "製造業/ものづくり"
    assert suggestion.tone_label.startswith("フォーマル")
    assert "サプライチェーンDX" in "\n".join(fields.values())


def test_generate_business_context_requires_basic_inputs():
    generator = BusinessContextGenerator()
    with pytest.raises(GenerationError):
        generator.generate_business_context(industry="", business_model="")


def test_generate_business_context_fallback_profile():
    generator = BusinessContextGenerator()
    suggestion = generator.generate_business_context(
        industry="教育サービス",
        business_model="オンライン講座",
        product="マネジメント研修",
        target_customer="新任マネージャー向け研修を検討する企業",
        tone="casual",
    )

    assert suggestion.profile_name == "汎用/プロフェッショナルサービス"
    assert suggestion.tone_label.startswith("カジュアル")
    assert "マネジメント研修" in suggestion.fields["three_c_company"]

