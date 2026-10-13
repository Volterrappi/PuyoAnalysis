# PuyoReview — ぷよぷよ録画振り返り・盤面解析ツール

ぷよぷよeスポーツの対戦動画を振り返り、盤面を解析するWindows向けの**非公式ツール**です。

**Pythonのソースコードを公開する方針です。** 初めてPythonを使う人も、下の手順どおりに進めれば起動できるようにしています。

> **公開準備中**：初心者向けソースZIP `PuyoReview-Source-v1.0.0-EasySetup.zip` は作成済みですが、現時点でGitHub Releaseへの登録・一般公開はまだ行っていません。配布準備が整うまではダウンロードできません。GitHubの「Code → Download ZIP」には起動に必要な配布ファイルが揃っていない場合があります。

## はじめかた（Windows 10/11・64bit）

### 1. Python 3.12を入れる（最初の1回だけ）

[Python公式サイト](https://www.python.org/downloads/) から**Python 3.12（64bit）**をインストールします。インストール画面に **Python Launcher** があれば有効にしてください。

Windowsの「コマンドプロンプト」を開き、次を入力します。

```cmd
py -3.12 --version
```

`Python 3.12.x` と表示されたら準備OK。Python 3.13/3.14しか入っていない場合は、3.12も追加でインストールしてください。

### 2. ソースZIPをダウンロードして展開

[GitHub Releases](https://github.com/Volterrappi/PuyoReview-Release/releases) に今後掲載する **`PuyoReview-Source-v1.0.0-EasySetup.zip`** をダウンロードし、右クリック→「すべて展開」します。

### 3. `SETUP_FIRST.bat` をダブルクリック

展開したフォルダにある **`SETUP_FIRST.bat`** をダブルクリックすると、必要なライブラリを自動インストールします。Python以外のライブラリを一つずつ手動で入れる必要はありません。

初回のみインターネット接続が必要です。黒い画面に `Libraries OK` と `Setup complete` が出たら成功。

`.venv` という専用フォルダへインストールするので、PC内の他のPython環境とは分けて管理されます。

### 4. 起動したいツールをダブルクリック

| 起動ファイル | 内容 |
| --- | --- |
| `START_Review.bat` | 動画振り返り＋盤面解析の全体版 |
| `START_Analysis.bat` | 盤面解析だけの単体版 |

**次回からはセットアップ不要**。使いたいSTARTファイルをダブルクリックするだけです。

## 主な機能（v28）

- MP4・YouTubeの対戦動画を再生して盤面キャプチャ・振り返り記録を作成（全体版）
- 手入力、画像ファイル、クリップボード画像からの盤面認識
- 連鎖数・得点・フレーム数・効率の表示と連鎖アニメーション
- NEXT3組を用いた3手全探索と、盤面推移の表示
- 盤面・NEXTの保存と復元

## うまく起動しないとき

| 表示・症状 | 対処 |
| --- | --- |
| `Python 3.12 (64-bit) ... not found` | Python公式サイトから3.12（64bit）とPython Launcherを入れる |
| `Installation failed` | インターネット・ディスク空き容量を確認し、`SETUP_FIRST.bat` を再実行 |
| `ModuleNotFoundError` | セットアップが完了していない可能性あり。`SETUP_FIRST.bat` を再実行 |
| YouTube画面が出ない | [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) を確認。埋め込み制限のある動画もあります |

再セットアップする場合は、アプリ終了後に展開フォルダ内の **`.venv` だけ**を削除して `SETUP_FIRST.bat` を再実行してください。

保存済みの記録は `%USERPROFILE%\PuyoReview` に置かれます。更新や再セットアップ時にこのフォルダを削除しないでください。

## 技術的な説明（慣れている方向け）

Windows + Python 3.12、GUIはTkinter・pywebview、画像処理はPillow・OpenCV、Windows連携はpythonnetです。依存ライブラリは `requirements-windows.txt` に動作確認済みのバージョンを固定しています。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\.venv\Scripts\python.exe review.py
```

盤面解析だけなら `.\.venv\Scripts\python.exe puyo_tools\app.py` です。

## 注意事項・利用条件

- MP4再生は現状、映像のみ（音声なし）。
- 全探索ではゲーム内の操作可能性や回し入れを厳密には判定していません。置けない候補が含まれる場合があります。
- YouTubeは公式埋め込みプレイヤーを利用し、動画をダウンロードしません。
- これはファン制作の非公式ツールです。ゲームや名称等の権利は各権利者に帰属します。
- **ソース公開とMITなどのオープンソースライセンスでの配布は別です。** 現在、独自ソース・自作画像は閲覧と個人利用を許可する条件で準備しています。詳しくは [TERMS.md](TERMS.md)。
- 外部依存は各ライブラリのライセンスに従います。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。

不具合・機能要望は [X：@istnpypy](https://x.com/istnpypy) または [GitHub Issues](https://github.com/Volterrappi/PuyoReview-Release/issues) へお願いします。
