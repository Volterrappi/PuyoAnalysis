# v1.0.0 ソース版の公開前チェック（2026-10-13 更新）

## Windows実機チェック（ユーザー確認済み）
- [x] 新しいZIPを別フォルダに展開して SETUP_FIRST.bat で Libraries OK / Setup complete
- [x] START_Analysis.bat で盤面入力、連鎖STATS、3手全探索
- [x] START_Review.bat でMP4再生、盤面キャプチャ
- [x] YouTube再生・一時停止・盤面取り込み
- [x] 振り返り記録の保存とアプリ再起動後の読み込み

## GitHub側の確認
- [x] 開発元 Volterrappi/PuyoReview はPrivateのまま
- [x] 公開用 Volterrappi/PuyoReview-Release はPublic
- [x] 公開用READMEにセットアップ手順・既知の制約を記載
- [x] バージョン固定の requirements-windows.txt がある
- [x] TERMS.md と THIRD_PARTY_NOTICES.md がある
- [x] Release v1.0.0 はDraft（未公開）
- [x] ソースZIP PuyoReview-Source-Windows-v1.0.0.zip がDraft添付済み（GitHub表示64,300バイト）
- [x] Private / Public 両リポジトリで同じパスの主要ソースをGit blob SHAで照合（21ファイル一致）

## YouTube機能を初回公開から除外する決定（2026-10-13）
- [x] ユーザー判断：YouTube機能なしで初回公開する
- [x] GitHub公開用 review.py の起動ボタンを除去し、YouTube起動メソッドを無効化
- [x] README.md、RELEASE_NOTES_SOURCE.md にYouTube機能無効を明示
- [ ] **重要：Draftに添付されたソースZIPは変更前のまま。更新済みreview.pyを含むZIPを再生成・再添付するまで公開しない**
- [ ] 最終ZIP内でYouTubeプレイヤー関連のコードを配布する必要があるか再確認（機能停止済みだがソース自体は現在リポジトリ内に存在）

## 公開前の必須確認と作業
- [ ] 実機確認したZIPとRelease添付ZIPが同一か、SHA-256等で照合する（GitHub添付ZIPのバイト単位検証は未実施）
- [ ] 旧EXE版の2つのZIP（PuyoReview-Windows.zip / PuyoAnalysis-Windows.zip）をDraftから削除または別Releaseへ分離する
- [ ] Release本文を RELEASE_NOTES_SOURCE.md に基づくソース版説明へ変更する
- [ ] 利用した第三者ソース・画像の由来と必要なライセンス表示を最終確認する
- [x] YouTube機能は初回公開から除外する方針を決定（レビューUIと起動経路を無効化。ZIP反映は未完了）
- [ ] 最終配布ZIPのファイル一覧、個人情報、API鍵、不要なバイナリ・Git履歴が含まれないことを確認する
- [ ] 以上を確認したうえで Publish release（現状Draft維持）

- [ ] YouTube無効化後の最終ZIPで、MP4再生・解析・記録の簡易スモークテストを実施

## 任意の追加テスト
- [ ] 別Windows PC、またはクリーンなPython 3.12環境で再現確認
- [ ] 異常URL、破損MP4、空入力などのエラー処理を確認

## 注意
- 開発用PrivateリポジトリをPublicにしない（Git履歴に個人メールアドレスの懸念）。
- Private側の scripts/package_source_release.py は旧24ファイル構成で、公開用セットアップBATを含まない。現在のWindows用配布ZIP生成方法として再利用しない。
- 自作コードの公開条件はTERMS.md（MIT等のオープンソース許諾ではない）。
- 現在のRelease Draftには旧EXE版ZIPが残り、本文も旧EXE版について述べている。確認前にPublishしない。
