# Windowsセットアップ手順（ビルドツール不要版）

## 推奨（最も簡単）: Python 3.12 で仮想環境を作成
1. Python 3.12 をインストール（すでに 3.13 のみの場合でも 3.12 を併用可）。
2. コマンドプロンプトまたはPowerShellで:  
   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   streamlit run app.py
   ```

## 3.13 を使いたい場合
- `requirements.txt` は Python 3.13 向けに `pandas>=2.2.3` / `matplotlib>=3.9.0` / `numpy>=2.1.0` を指定済みです。
- それでも **Preparing metadata (pyproject.toml)** エラーが出る場合は、
  1) `pip` を最新化し、
  2) wheel のみを許可して再試行してください。  
   ```powershell
   python -m pip install --upgrade pip
   pip install --only-binary=:all: -r requirements.txt
   ```
  これでwheelが見つからない場合は当該バージョンのwheelが未提供です。Python 3.12での実行をご検討ください。

## よくあるエラー
- `Could not find vswhere.exe` が表示される:  
  wheelが見つからず **ソースからビルド** しようとしています。Visual Studio Build Tools を入れる代わりに、
  **上記のPython 3.12手順** か **--only-binaryオプション** をご利用ください。
