# YouTube連携機能の条項別評価（2026-10-14 調査メモ）

**結論：現時点ではYouTube自動キャプチャ機能を公開しない。** 公式プレイヤーの埋め込み表示は原則として許容されるが、画面画像の取得・保存に包括的な許可や例外は確認できない。以下は規約の構造を機能別に整理したもので、法的な確定判断ではない。

## 適用文書の階層
1. **YouTube一般利用規約（Permissions and Restrictions）**：サービスを利用する全般の条件。埋め込みプレイヤーによる表示を認めつつ、コンテンツの複製等を原則制限。例外はYouTubeによる明示許可／権利者を含む書面許諾／適用法令による許可（地域・版による表現差に注意）。
2. **YouTube API Services Terms of Service**：YouTube API Servicesを利用するAPI Clientの契約。IFrame Player APIも関連サービスのため、開発者ポリシーとMinimum Functionalityを検討する。
3. **Developer Policies III.E.1.a**：事前のYouTubeの書面承認なくYouTube audiovisual contentのコピーをdownload/import/backup/cache/storeすることを禁止。**「自分がアップロードした動画」「短い静止画像」「私的な分析」だから一般的に免除、とは書かれていない。**
4. **Developer Policies III.I.6/7/14**：プレイヤーの一部の改変、映像音声成分の分離・変更、API以外の技術でのAPI Data/映像部分の取得をそれぞれ禁止。III.I.1はYouTubeの中核体験の模倣を禁じるが、独立した付加価値について例外余地がある。**III.I.1の価値付加の例外をIII.E.1やIII.I.14へ横滑りさせてはいけない。**
5. **Required Minimum Functionality: YouTube embedded player**：HTTP RefererによるアプリID提示、プレイヤーサイズ、プレイヤーUI・広告・コントロールを妨げない表示等。特にWebView上のRefererは要検証。

## 機能別マトリクス（OK / NG / 分岐）

| 機能 | 条文の原則と例外 | OKとなる読み方・条件 | NGとなる読み方・条件 | 現判断 |
|---|---|---|---|---|
| 公式iframeで再生 | 一般規約は埋め込み表示を許容。API規約とMinimum Functionalityが追加適用 | 正規IFrame API、UI・広告維持、必要なReferer送信、埋め込みが許された動画 | 埋め込み不可動画、Referer未設定、広告やブランドを隠す、不正な方法での再生 | 条件付きOK、現コードではReferer未検証 |
| 一時停止・時刻取得 | IFrame Player APIの文書化された呼び出しは使用可能 | pauseVideo/getCurrentTimeなど公式公開メソッドの通常利用 | 非公開API解析、プレイヤー回避、意図しない再生操作 | 原則OK |
| プレイヤー画面をOSキャプチャ | III.E.1.aのコピー、III.I.14の非API技術による映像取得との関係 | **許容を主張するなら** 画像1枚は「audiovisual contentのcopy」ではない、または別途書面承認・適用可能な例外が及ぶ、と読む必要がある。ただし公式な根拠不足 | 静止画も映像の一部分のcopyでありOS画面取得がnon-API technologyによる取得なら禁止 | NGリスク高、公開保留 |
| キャプチャを盤面に切り抜く | III.I.7映像成分の分離・変更、III.E.1.a | ユーザーが独立して用意した非YouTube由来の入力画像を解析するだけでAPI Dataに触れない | APIプレイヤーから自動取得した映像の一部分を加工・保存 | 自動取得は公開保留 |
| 盤面の色を認識して文字列化 | API Dataからの派生なのか独立したゲーム状態の生成なのかが焦点 | 手入力やユーザー指定のローカル画像から、独自計算で盤面データを作る | API Dataから無断で導出したデータ・メトリクスとしてIII.E.4.8等に該当 | 手入力・独立ローカル画像は低リスク、YouTube自動取得由来は要確認 |
| 自作盤面・解析結果をJSON保存 | 保存対象がYouTubeの「audiovisual content」「API Data」に該当するか | ユーザー作成の盤面テキスト・独自計算結果は通常YouTube動画のコピーではない | 動画画面画像・API Data自体を同梱、あるいはAPI Dataの無許可派生物を保存 | 独立入力はOK寄り |
| ユーザーがクリップボードから画像入力 | 開発者API契約の適用範囲／元画像の取得経緯を区別 | アプリがYouTube接続せず、任意のローカル画像を読み取る汎用画像機能。本人が権利を持つ画像等 | 実質的にYouTubeをキャプチャする方法を誘導・自動化する設計、権利者の許可がない複製 | 汎用の画像入力は比較的低リスク。ただしユーザーが取得した全画像に権利があるとは保証できない |
| 動画URL・タイムスタンプをメモ保存 | API Dataか、ユーザーが入力した単なる参照か | URLをユーザーの記録メモとして保持し、公式サイトへの通常リンクを提供するだけ | APIで取得したタイトル等の保存制限を無視する、プレイヤーへのアクセスを偽装する | URLだけなら概ね低リスク、メタデータAPI連携は別途確認 |
| 保存記録から同じYouTube動画へジャンプ | 通常のリンク／公式プレイヤーへのアクセス | 公式YouTubeへ時刻付きURLで遷移、または要件を満たした埋め込み | 非公式プレイヤー、取得禁止や広告回避がある | リンク方式なら低リスク |
| 非表示/バックグラウンド再生 | III.I.9がbackground playerを禁止 | 通常の可視プレイヤーでユーザー操作に従い再生 | 非表示ウィンドウで自動再生・自動解析 | NG |

## 条文構造に関する重要な留保
- **禁止の例外は条文ごとに異なる。** 一般規約の法令例外や、III.I.1の「独立の付加価値」は、III.I.14の明確な取得手段の禁止を直ちに解除しない。
- **法律とAPI契約は別レイヤー。** 著作権法上の私的複製等が成立し得ても、開発者に契約上許されているとは限らない。逆にアプリの汎用クリップボード解析はYouTube APIを使わない限り、その部分だけでYouTube API Clientの行為にはならない。
- **一枚の停止画面が禁止される「audiovisual contentのコピー」か**、**OSで取得した画像がIII.I.14の「access or retrieve any portion」に該当するか**は、最終的に公式解釈・書面承認が必要となる曖昧点。
- **自分の動画なら大丈夫**：著作権者の許諾とYouTube API規約上の書面承認は別。「投稿者だからIII.E.1.a免除」の明文は見つからない。
- 著作権・個人情報・配信プラットフォームのルールも別途適用され得る。

## 規約を回避する設計（迂回・隠蔽ではなく非該当化）
1. 解析単体版はYouTube接続を行わず、ユーザー提供の盤面テキスト・ローカル画像・クリップボード画像を受け取る。
2. 動画確認はユーザーが通常のYouTubeサイト上で実行し、PuyoReviewは映像を取得しない。リンクや時刻文字列の記録は任意入力にとどめる。
3. 公式埋め込みを再開する場合はプレイヤーのReferer要件等を満たし、画像取得・保存なしの機能から再テスト。
4. 自動キャプチャを再開したければ、YouTubeにIII.E.1.a／III.I.14／III.I.7の具体的な適用関係を書面で問い合わせる。口頭解釈や「一瞬だけ」ではリスク解消とならない。

## 公式参照先
- YouTube一般規約：https://www.youtube.com/t/terms
- YouTube API Developer Policies：https://developers.google.com/youtube/terms/developer-policies
- YouTube API Required Minimum Functionality：https://developers.google.com/youtube/terms/required-minimum-functionality
- YouTube API Compliance Guide：https://developers.google.com/youtube/terms/developer-policies-guide
- YouTube API Terms：https://developers.google.com/youtube/terms/api-services-terms-of-service

この文書は技術・規約の読み取りメモであって、法律意見書ではない。
