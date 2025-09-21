# 経営計画策定WEBアプリ（Streamlit版）

## 使い方
1. Python 3.10+ を用意してください。
2. 仮想環境を作成し、依存関係をインストールします。

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. アプリを起動します。

```bash
streamlit run app.py
```

## 機能概要
- 単年利益計画（売上、外部仕入、内部費用、営業外）
- KPI（損益分岐点、一人当たり、労働分配率）
- シナリオ比較（売上±、粗利±、目標経常、昨年同一、BEP）
- 感応度分析（トルネード図）
- Excelエクスポート（数値/KPI/感応度）

## 注意
- 計算はすべて「円」ベース、表示のみ「百万円/千円/円」を切替。
- 金額上書きは率より優先（固定費扱い）。
- 目標経常利益の逆算は二分探索で±1,000円まで収束。
