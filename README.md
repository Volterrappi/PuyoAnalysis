# PuyoReview — ぷよぷよ録画振り返り・盤面解析

ぷよぷよeスポーツの対戦動画を振り返り、連鎖の解析やNEXT3組の3手全探索ができる、**Windows向けの非公式Pythonツール**です。

> **公開準備中**：現在、配布用のソースZIPを準備しています。Releasesに表示されるまでは、下記のダウンロード手順は実行できません。開発用リポジトリはPrivateのままです。

## できること

- MP4・YouTube動画を見ながら盤面をキャプチャし、振り返り記録を保存（全体版）
- 手入力・スクリーンショット・クリップボードから盤面を読み取り
- 連鎖数・得点・フレーム数・効率を計算し、アニメーションで表示
- NEXT3組を入力して**3手全探索**、各手の盤面変化を確認
- 盤面やNEXTの保存・読み込み

## 初めて使う人向け：インストールと起動

Python以外のライブラリを個別に探して入れる必要はありません。専用のセットアップBATがまとめてインストールします。

### ① Pythonをインストール

1. [Python公式サイト](https://www.python.org/downloads/) から **Windows用・64bitのPython 3.12以上**をインストールします。
2. インストール画面で **Python Launcher（pyコマンド）** を含めます（`Add python.exe to PATH` があればチェック推奨）。
3. Windowsの「コマンドプロンプト」を開いて `py --version` を入力します。Python 3.12以降と表示されればOKです。

| Python | セットアップの扱い |
| --- | --- |
| 3.11以前 | 対応対象外、エラー停止 |
| 3.12 | 通常実行 |
| 3.13以上 | 注意メッセージを表示して実行続行 |

**Python 3.13.14は開発者のWindows PCでセットアップ・起動確認済み**です。すべてのPythonのバージョンでの動作を保証するものではありません。

### ② ソースZIPをダウンロード・展開

[Releases（ダウンロードページ）](https://github.com/Volterrappi/PuyoReview-Release/releases) から **`PuyoReview-Source-v1.0.0-EasySetup-Python312plus.zip`** をダウンロードします。

ZIPを右クリックして「すべて展開」を選び、展開されたフォルダを開きます。

### ③ `SETUP_FIRST.bat` をダブルクリック

初回だけ `SETUP_FIRST.bat` を実行してください。次のライブラリを専用環境 `.venv` にまとめてインストールします。

- Pillow：画像処理
- OpenCV：画像認識・MP4動画処理
- pywebview：YouTube表示
- pythonnet：Windows/.NET連携

インストール中はインターネット接続が必要です。画面に **`Libraries OK`** と **`Setup complete`** が出れば完了です。

### ④ 起動する

| ダブルクリックするファイル | 使える機能 |
| --- | --- |
| **`START_Review.bat`** | 動画振り返り＋盤面解析（全体版） |
| **`START_Analysis.bat`** | 盤面解析のみ |

次回から `SETUP_FIRST.bat` は不要です。起動用BATを実行してください。

## 困ったとき

**`py` が見つからない／Pythonのバージョンが古い**

Python 3.12以上の64bit版を公式サイトから導入し、Python Launcherが入っているか確認してください。コマンドプロンプトで `py -0p` と入力するとインストール済みのPythonが一覧表示されます。

**`Installation failed` や `ModuleNotFoundError` が出る**

ネット接続・ディスク容量を確認して `SETUP_FIRST.bat` を再度実行します。それでも解決しなければ、表示されたエラーメッセージを報告してください。

**セットアップ環境を作り直したい**

ツールを終了し、展開したフォルダ内の **`.venv` だけ**を削除してから `SETUP_FIRST.bat` を再実行します。保存済みの振り返り記録がある `%USERPROFILE%\PuyoReview` は削除しないでください。

**YouTubeが表示されない**

[Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) があるか確認してください。動画の埋め込み制限でも表示できない場合があります。

## 動作環境と既知の制約

- Windows 10 / 11（64bit）向け。Python 3.12で自動テスト、3.13.14で開発者によるセットアップ・起動確認済み
- MP4再生は映像のみ（音声なし）
- 全探索は厳密な操作可能性・回し入れ判定を行わず、実際に置けない候補が含まれる可能性あり
- YouTubeは公式の埋め込みプレイヤーを使用し、動画をダウンロードしません
- 記録の保存先は `%USERPROFILE%\PuyoReview`
- 本ツールは非公式のファン制作ツールで、ゲームの開発・販売元とは無関係です

## ソース公開とライセンス

ソース配布形式です。第三者ライブラリのDLLやEXEはソースZIPに同梱せず、ユーザーの環境でインストールします。

**ソースを読めることと、MITなどのオープンソースライセンスで公開することは別です。** 現在、独自コードと自作画像の利用条件は [TERMS.md](TERMS.md)、依存ライブラリは [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に記載しています。

不具合や要望：**[X @istnpypy](https://x.com/istnpypy)** ／ [GitHub Issues](https://github.com/Volterrappi/PuyoReview-Release/issues)

報告時は個人情報・動画の非公開URL・APIキー等を投稿しないでください。
