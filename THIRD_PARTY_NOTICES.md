# 第三者コンポーネントについて

このアプリはPythonで開発され、Windows版の作成にPyInstallerを利用しています。実行環境および同梱ライブラリはそれぞれのライセンスに従います。主に次のプロジェクトを利用しています。

| コンポーネント | 用途 | 公式サイト |
| --- | --- | --- |
| Python / Python標準ライブラリ | 実行環境 | https://www.python.org/ |
| Pillow | 画像処理・クリップボード画像 | https://python-pillow.github.io/ |
| OpenCV / opencv-python | 画像処理 | https://opencv.org/ |
| pywebview | YouTube表示のWebView | https://pywebview.flowrl.com/ |
| pythonnet | Windows/.NET連携 | https://pythonnet.github.io/ |
| PyInstaller | Windows向けEXE作成 | https://pyinstaller.org/ |
| Microsoft Edge WebView2 | YouTubeプレイヤー表示に利用 | https://developer.microsoft.com/microsoft-edge/webview2/ |

**OpenCV/FFmpegに関する注意**：`opencv-python` の公式配布wheelはFFmpegを含み、LGPL 2.1の条件が関係します。単にライセンス文を同梱するだけでなく、適用される条件に応じてFFmpegの対応するソースの提供・入手案内や再リンク可能性等の確認が必要です。公式の [opencv-python 第三者ライセンス](https://github.com/opencv/opencv-python/blob/4.x/LICENSE-3RD-PARTY.txt) を参照してください。

この一覧は主要な直接依存関係を示すもので、すべての再帰的依存関係・著作権表示の網羅を保証するものではありません。各コンポーネントの著作権表示、ライセンス全文、必要な再配布通知の適用については、配布ZIPに同梱される各ライブラリおよび公式のライセンス情報を確認してください。

PuyoReview本体の利用条件は [TERMS.md](TERMS.md) にあります。**これらの第三者ライセンスが、PuyoReview自体のソースコードの自由利用を認めるものではありません。**
