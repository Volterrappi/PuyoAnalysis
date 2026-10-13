# v1.0.0 ソース版の公開前チェック（配布管理者向け）

## Release下書き
- [ ] 旧EXE配布用の `PuyoReview-Windows.zip` と `PuyoAnalysis-Windows.zip` をDraftから削除する
- [ ] 新しい `PuyoReview-Source-Windows-v1.0.0.zip` をRelease assetsに添付する
- [ ] Release notesをソース版用の説明に変更する（EXE起動の手順を残さない）
- [ ] GitHub上のREADMEからの導線・ZIPの中身が一致することを確認する
- [ ] 実機テスト後に `Publish release` する（現時点ではDraft維持）

## 利用者環境で試す
- [ ] Python 3.13.14で `SETUP_FIRST.bat` を実行し、バージョン警告が出た後も `Libraries OK` と `Setup complete` まで到達する
- [ ] `START_Analysis.bat` で手入力→連鎖STATS→NEXT3組の3手全探索→結果画面を確認する
- [ ] `START_Review.bat` でMP4の再生・停止・画像取り込みを確認する
- [ ] YouTube URLから動画を再生し、停止・盤面への取り込みを確認する
- [ ] 振り返り記録を保存し、再起動後も開けることを確認する
- [ ] 新しいフォルダに展開し、既存の`.venv`に依存せずセットアップを完了できることを確認する

## 留意点
- **開発用PrivateリポジトリをPublicにしないこと**（旧コミットのメールアドレスが露出するため）
- ソース版のZIPには開発Git履歴・第三者バイナリを含めない
- コードを公開することと、MIT等による自由な改変・再配布許可は別。利用条件は `TERMS.md`
- 開発者が確認できていない環境・機能については「動作保証」と書かない

確認時に問題があれば、ZIPはそのままDraftに置き、修正して差し替える。
