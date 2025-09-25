"""Utility for generating business context drafts from lightweight inputs."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Sequence

__all__ = [
    "BusinessContextGenerator",
    "BusinessContextSuggestion",
    "GenerationError",
    "IndustryProfile",
]


@dataclass(frozen=True)
class IndustryProfile:
    """Reference description used to tailor generated sentences."""

    name: str
    keywords: Sequence[str]
    default_customer: str
    decision_maker: str
    buying_trigger: str
    pain_points: str
    trend: str
    solution: str
    strengths: str
    competitor_landscape: str
    differentiator: str
    channel_strategy: str
    kpi_focus: str
    action_note: str


@dataclass
class BusinessContextSuggestion:
    """Result payload returned by :class:`BusinessContextGenerator`."""

    profile_name: str
    tone_key: str
    tone_label: str
    fields: Dict[str, str]
    highlights: List[str]


class GenerationError(ValueError):
    """Raised when required inputs for suggestion generation are missing."""


class BusinessContextGenerator:
    """Produce short-form business context write-ups from simple keywords."""

    _tone_styles: Dict[str, Dict[str, str]] = {
        "standard": {
            "label": "標準（事業計画書向け）",
            "closing": "を目指します。",
            "commit": "伴走しながら価値創出を進めていきます。",
        },
        "formal": {
            "label": "フォーマル（金融機関・取引先向け）",
            "closing": "を目指してまいります。",
            "commit": "伴走しながら価値創出を推進してまいります。",
        },
        "casual": {
            "label": "カジュアル（社内共有向け）",
            "closing": "を狙っていきます。",
            "commit": "チーム一体で価値創出を加速していきます。",
        },
    }

    _profiles: Sequence[IndustryProfile] = (
        IndustryProfile(
            name="製造業/ものづくり",
            keywords=("製造", "工場", "ものづくり", "メーカー", "製造業"),
            default_customer="従業員100〜500名の製造業（自動車部品・金属加工など）",
            decision_maker="生産管理部門長・工場長・経営企画",
            buying_trigger="在庫過多や生産リードタイムの長期化が顕在化したタイミング",
            pain_points="多品種少量生産への対応や需給予測の精度が低く、在庫回転日数が長期化しています。",
            trend="IoT/センサー活用やGX対応が進み、デジタルによる現場改善ニーズが高まっています。",
            solution="生産計画・在庫を見える化し、需要変動にも柔軟に追随できる運用体制を構築します。",
            strengths="製造現場の知見を持つコンサルタントとデータエンジニアが導入から定着まで支援します。",
            competitor_landscape="大手ERPベンダーや地場SIerが既存システムを提供していますが、現場運用に寄り添った改善が遅れています。",
            differentiator="現場データの統合とダッシュボード化を短期間で実現するテンプレートとアナリティクスを備えています。",
            channel_strategy="製造業向け展示会、業界団体セミナー、地域金融機関との協業を通じた紹介案件を中心に開拓します。",
            kpi_focus="在庫回転日数45日以内、設備稼働率85%以上、不良率1%未満を指標とします。",
            action_note="現場ヒアリングとデジタルツールの習熟を四半期ごとにレビューし、改善サイクルを内製化",
        ),
        IndustryProfile(
            name="SaaS/ITサービス",
            keywords=("SaaS", "クラウド", "ITサービス", "DX", "サブスク"),
            default_customer="従業員50〜300名の中堅企業 情報システム部門",
            decision_maker="情報システム部長・DX推進責任者・経営層",
            buying_trigger="業務の属人化・複数システムの乱立による運用負荷が限界に達したタイミング",
            pain_points="レガシーシステムが残り、手作業やExcel集計が多く運用コストが高止まりしています。",
            trend="クラウド移行とリモートワークの定着で、セキュリティと運用効率を両立するSaaSへの移行が進んでいます。",
            solution="導入から90日で主要業務をデジタル化し、運用コストを20%削減する再現性の高いオンボーディングを提供します。",
            strengths="業界別テンプレートとAPI連携群、カスタマーサクセスチームによる伴走で解約率を抑制します。",
            competitor_landscape="大手プラットフォームや汎用ツールが競合ですが、業務要件への適合度とサポートが限定的です。",
            differentiator="業種特化ワークフローと継続的な活用支援プログラムで成果創出を下支えします。",
            channel_strategy="ウェビナー・SEO等のインバウンドとパートナーセールス、既存顧客紹介を組み合わせたハイブリッド体制です。",
            kpi_focus="月次解約率0.6%以下、LTV/CAC 3倍、ARR成長率20%以上を重点KPIとします。",
            action_note="ユーザーコミュニティ運営とQBRで活用度を計測し、ロードマップへ素早く反映",
        ),
        IndustryProfile(
            name="小売/EC",
            keywords=("小売", "リテール", "EC", "通販", "物販"),
            default_customer="年商5〜30億円規模の専門店・D2Cブランド",
            decision_maker="営業企画責任者・ECマネージャー・店舗統括",
            buying_trigger="在庫回転率やデジタル広告ROIの悪化が顕在化したタイミング",
            pain_points="チャネルごとの需要予測が難しく、在庫過多や欠品が同時に発生しています。",
            trend="オムニチャネル化とサステナビリティ対応が求められ、需給最適化と顧客体験強化が急務です。",
            solution="チャネル横断の売上・在庫データを統合し、販促計画と連動した需給最適化を実現します。",
            strengths="POS・EC・マーケティングデータを高速に取り込み、ダッシュボード化する標準アダプターを保有します。",
            competitor_landscape="大手コンサルや広告代理店が改善提案を行いますが、実行フェーズの伴走が限定的です。",
            differentiator="店舗とEC双方のKPIを可視化し、施策別の因果関係を検証できる分析テンプレートを提供します。",
            channel_strategy="デジタルマーケ、業界誌タイアップ、物流企業との共催セミナーで見込み顧客を獲得します。",
            kpi_focus="在庫回転日数40日以内、リピート購入率30%、広告ROI 200%以上を追求します。",
            action_note="MD会議でのダッシュボード活用を標準化し、効果検証サイクルを月次で運用",
        ),
        IndustryProfile(
            name="飲食/サービス業",
            keywords=("飲食", "外食", "レストラン", "フード", "サービス業"),
            default_customer="直営・FC合わせて10〜50店舗規模の外食チェーン",
            decision_maker="経営者・店舗統括マネージャー・業務改善リーダー",
            buying_trigger="FLコストの高止まりや店舗オペレーションの属人化が顕在化したタイミング",
            pain_points="人件費と原価が高止まりし、店長のマネジメント負荷も高く離職率が上昇しています。",
            trend="省人化投資とデータ活用のニーズが高まり、店舗マネジメントの標準化が求められています。",
            solution="需要予測と勤怠・仕入れデータを統合し、FLコスト最適化と店舗オペレーションの標準化を支援します。",
            strengths="店舗業務に精通したコンサルタントとマニュアル・教育コンテンツをセットで提供します。",
            competitor_landscape="大手POSベンダーやチェーン向けBPOが競合ですが、改善の実装まで踏み込めていません。",
            differentiator="AI需要予測とシフト最適化アルゴリズムで、売上機会損失と過剰人員を同時に抑制します。",
            channel_strategy="業界展示会、飲食店向けメディア、フランチャイズ本部との協業で案件化します。",
            kpi_focus="FLコスト60%以内、客単価+5%、スタッフ定着率85%以上を目標とします。",
            action_note="標準オペレーションの定着化と人材育成をセットで回し、PDCAを月次でレビュー",
        ),
        IndustryProfile(
            name="医療・ヘルスケア",
            keywords=("医療", "ヘルスケア", "クリニック", "介護", "ヘルス"),
            default_customer="地域密着型クリニック・介護事業者・ヘルスケア関連企業",
            decision_maker="院長・施設長・経営管理部門",
            buying_trigger="診療報酬改定や人材不足への対応が急務となったタイミング",
            pain_points="人材確保の難しさとコンプライアンス遵守の両立に負荷がかかり、業務効率化が課題です。",
            trend="地域包括ケアやデジタルヘルスの進展で、データ連携と患者体験の向上が求められています。",
            solution="患者・利用者データと業務プロセスを一元管理し、医療品質と稼働率を高める運用を支援します。",
            strengths="医療制度に精通した専門チームとセキュリティ設計ノウハウで安心して導入できます。",
            competitor_landscape="電子カルテベンダーやBPO事業者が存在しますが、経営改善の視点が限定的です。",
            differentiator="医療・介護双方のデータ連携実績と品質指標を可視化するダッシュボードを保有します。",
            channel_strategy="医師会・介護事業者向けセミナーや医療機器メーカーとの協業で信頼を醸成します。",
            kpi_focus="稼働率85%以上、患者/利用者満足度向上、スタッフ離職率低下を重点指標に据えます。",
            action_note="法制度アップデートと現場課題を定例で共有し、改善計画を迅速に修正",
        ),
        IndustryProfile(
            name="汎用/プロフェッショナルサービス",
            keywords=("",),
            default_customer="主要顧客の属性や課題に合わせて柔軟に設定",
            decision_maker="意思決定者の役職やチーム構成を明確化",
            buying_trigger="課題が顕在化し、改善の打ち手を検討し始めたタイミング",
            pain_points="顧客課題や市場環境を整理し、優先度の高い解決テーマを特定します。",
            trend="業界共通のトレンドを踏まえ、競合との差別化ポイントを明確にしていきます。",
            solution="提供価値・成果指標・支援体制を定義し、短期施策と中長期施策を組み合わせて進めます。",
            strengths="実績・専門性・ネットワークなど、顧客価値につながるリソースを棚卸します。",
            competitor_landscape="競合他社や代替手段の特徴を整理し、比較優位と補完関係を明示します。",
            differentiator="導入後の成功状態を共通認識化し、成果創出までのロードマップを提示します。",
            channel_strategy="既存顧客からの紹介、共催セミナー、デジタル施策など最適なチャネルを組み合わせます。",
            kpi_focus="売上・利益以外にも顧客満足度や稼働率など、重要指標を設定します。",
            action_note="共通KPIをモニタリングし、定例MTGで改善サイクルを回します",
        ),
    )

    def tone_presets(self) -> Dict[str, str]:
        """Return selectable tone presets mapped to display labels."""

        return {key: style["label"] for key, style in self._tone_styles.items()}

    def generate_business_context(
        self,
        *,
        industry: str,
        business_model: str,
        target_customer: str | None = None,
        product: str | None = None,
        keywords: Iterable[str] | str | None = None,
        tone: str = "standard",
    ) -> BusinessContextSuggestion:
        """Generate a structured business context draft.

        Parameters
        ----------
        industry:
            Industry or market the business belongs to.
        business_model:
            Business model or service category description.
        target_customer:
            Optional textual description of the primary customer.
        product:
            Optional product or service name.
        keywords:
            Iterable of emphasis keywords or a comma separated string.
        tone:
            Tone key, defaults to ``"standard"``.
        """

        normalized_industry = str(industry or "").strip()
        normalized_model = str(business_model or "").strip()
        if not normalized_industry and not normalized_model:
            raise GenerationError("業種または業態を入力してください。")

        selected_profile = self._resolve_profile(
            normalized_industry,
            normalized_model,
            product,
            target_customer,
            keywords,
        )

        tone_key = tone if tone in self._tone_styles else "standard"
        tone_style = self._tone_styles[tone_key]
        tone_label = tone_style["label"]

        keywords_list = self._normalize_keywords(keywords)

        target_description = (
            str(target_customer).strip()
            if target_customer and str(target_customer).strip()
            else selected_profile.default_customer
        )
        product_description = (
            str(product).strip()
            if product and str(product).strip()
            else (normalized_model or f"{normalized_industry}向けサービス")
        )

        context_fields: Dict[str, str] = {
            "three_c_customer": self._compose_customer_section(
                profile=selected_profile,
                target_description=target_description,
            ),
            "three_c_company": self._compose_company_section(
                profile=selected_profile,
                product_description=product_description,
                keywords=keywords_list,
            ),
            "three_c_competitor": self._compose_competitor_section(selected_profile),
            "bmc_customer_segments": self._compose_segments_section(
                profile=selected_profile,
                target_description=target_description,
            ),
            "bmc_value_proposition": self._compose_value_section(
                profile=selected_profile,
                product_description=product_description,
                keywords=keywords_list,
            ),
            "bmc_channels": self._compose_channel_section(selected_profile),
            "qualitative_memo": self._compose_memo_section(
                profile=selected_profile,
                tone_style=tone_style,
            ),
        }

        highlights = self._build_highlights(
            profile=selected_profile,
            target_description=target_description,
            keywords=keywords_list,
        )

        return BusinessContextSuggestion(
            profile_name=selected_profile.name,
            tone_key=tone_key,
            tone_label=tone_label,
            fields=context_fields,
            highlights=highlights,
        )

    def _resolve_profile(
        self,
        industry: str,
        business_model: str,
        product: str | None,
        target_customer: str | None,
        keywords: Iterable[str] | str | None,
    ) -> IndustryProfile:
        search_tokens = " ".join(
            filter(
                None,
                [
                    industry,
                    business_model,
                    str(product or ""),
                    str(target_customer or ""),
                    " ".join(self._normalize_keywords(keywords)),
                ],
            )
        ).lower()

        for profile in self._profiles:
            for keyword in profile.keywords:
                if not keyword:
                    continue
                if keyword.lower() in search_tokens:
                    return profile
        return self._profiles[-1]

    @staticmethod
    def _compose_customer_section(
        *, profile: IndustryProfile, target_description: str
    ) -> str:
        lines = [
            f"主要顧客：{target_description}",
            profile.pain_points,
            profile.trend,
        ]
        return "\n".join(lines)

    @staticmethod
    def _compose_company_section(
        *,
        profile: IndustryProfile,
        product_description: str,
        keywords: List[str],
    ) -> str:
        lines = [
            f"当社は{product_description}を提供し、{profile.solution}",
            profile.strengths,
            f"差別化要素：{profile.differentiator}",
        ]
        if keywords:
            lines.append(f"注力キーワード：{', '.join(keywords)}")
        return "\n".join(lines)

    @staticmethod
    def _compose_competitor_section(profile: IndustryProfile) -> str:
        lines = [
            profile.competitor_landscape,
            f"当社の優位性：{profile.differentiator}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _compose_segments_section(
        *, profile: IndustryProfile, target_description: str
    ) -> str:
        lines = [
            f"- メインセグメント：{target_description}",
            f"- 意思決定者：{profile.decision_maker}",
            f"- 購買トリガー：{profile.buying_trigger}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _compose_value_section(
        *,
        profile: IndustryProfile,
        product_description: str,
        keywords: List[str],
    ) -> str:
        lines = [
            f"- 提供価値：{profile.solution}",
            f"- 成果指標：{profile.kpi_focus}",
            f"- サービス特長：{profile.strengths}",
        ]
        if keywords:
            lines.append(f"- 強調ポイント：{', '.join(keywords)}")
        lines.append(f"- プロダクト：{product_description}")
        return "\n".join(lines)

    @staticmethod
    def _compose_channel_section(profile: IndustryProfile) -> str:
        lines = [
            f"- 主なチャネル：{profile.channel_strategy}",
            "- ナーチャリング：顧客事例や導入効果レポートで意思決定を後押し",
        ]
        return "\n".join(lines)

    @staticmethod
    def _compose_memo_section(
        *, profile: IndustryProfile, tone_style: Dict[str, str]
    ) -> str:
        lines = [
            f"市場動向：{profile.trend}",
            f"重点KPI：{profile.kpi_focus}",
            f"実行方針：{profile.action_note}{tone_style['closing']}",
            f"体制：{tone_style['commit']}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_highlights(
        *,
        profile: IndustryProfile,
        target_description: str,
        keywords: List[str],
    ) -> List[str]:
        highlights = [
            f"ターゲット：{target_description}",
            f"KPI：{profile.kpi_focus}",
            f"チャネル戦略：{profile.channel_strategy}",
        ]
        if keywords:
            highlights.append(f"キーワード：{', '.join(keywords)}")
        return highlights

    @staticmethod
    def _normalize_keywords(keywords: Iterable[str] | str | None) -> List[str]:
        if keywords is None:
            return []
        if isinstance(keywords, str):
            raw_tokens = re.split(r"[、,;/\n]", keywords)
        else:
            raw_tokens = [str(token) for token in keywords]
        normalized: List[str] = []
        seen = set()
        for token in raw_tokens:
            value = token.strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(value)
        return normalized


__all__ = [
    "BusinessContextGenerator",
    "BusinessContextSuggestion",
    "GenerationError",
    "IndustryProfile",
]

