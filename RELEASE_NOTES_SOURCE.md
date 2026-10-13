# PuyoReview v1.0.0 — ソース公開版

ぷよぷよeスポーツの対戦動画を振り返り、盤面解析・連鎖STATS・NEXT3組の3手全探索を行うWindows向けの非公式Pythonツールです。

## ダウンロード
下の **Assets** から `PuyoReview-Source-Windows-v1.0.0.zip` をダウンロードして、「すべて展開」してください。

## はじめかた
1. Python公式サイトから**64bit版 Python 3.12以上**をインストール（Python Launcherを含める）。
2. 展開フォルダの **`SETUP_FIRST.bat`** をダブルクリック。必要なライブラリをまとめて自動インストールします。
3. `Libraries OK`、`Setup complete` と出たら成功。
4. **`START_Review.bat`**（動画振り返り＋解析）または **`START_Analysis.bat`**（解析単体）をダブルクリックして起動。

Python 3.11以前は非対応。Python 3.13以上では注意メッセージを表示した後、そのままセットアップを続行します。開発者環境のPython 3.13.14ではセットアップ・起動確認済みです。

詳しい手順、エラー対処は [README](https://github.com/Volterrappi/PuyoReview-Release#readme) を参照してください。

## 主な機能
- MP4・YouTube動画の振り返り、盤面キャプチャ、記録保存
- 手入力、画像、クリップボードから盤面を認識
- 連鎖数・得点・所要フレーム・効率の表示
- 連鎖アニメーション、NEXT3組の3手全探索
- 盤面とNEXTの保存・復元

## 注意事項
- Windows 10/11（64bit）向けで、初回セットアップにはインターネット接続が必要です。
- MP4は現状音声なし。全探索には、操作可能性の制約で実際には置けない候補が含まれる場合があります。
- この配布物はPythonソースを含みます。EXE・第三者ライブラリのバイナリは同梱していません。
- 非公式のファン制作ツールです。独自コード・画像の利用条件はZIP内の `TERMS.md` を参照してください。

不具合や要望は [X @istnpypy](https://x.com/istnpypy) までお願いします。
