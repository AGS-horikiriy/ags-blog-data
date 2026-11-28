# AGS Codex SQSP-Blogger — Public Data

SquarespaceとBloggerで共通利用する、AGSの公開Webデータと生成処理を保管します。開発・運用上の担当領域は **SQSP-Blogger（Codex）** です。

## リポジトリ名と公開URL

GitHubの実名は **`ags-blog-data`** を維持します。SQSP-Blogger領域への管理統合に伴って、既存URLを直ちに変更するものではありません。

- Repository: https://github.com/AGS-horikiriy/ags-blog-data
- GitHub Pages: https://ags-horikiriy.github.io/ags-blog-data/

開発案、非公開レビュー、Squarespace/Bloggerの変更前後の原本・復元記録は、非公開の共通Web管理リポジトリ（変更先名 `ags-codex-sqsp-blogger`）に集約する方針です。公開用データ配信はこのリポジトリが担います。

## 配信ファイルと互換性

| ファイル | JavaScriptのデータ名 | 内容 |
| --- | --- | --- |
| `word_counts.js` | `AGS_WORD_COUNTS` | 記事URLごとの語数 |
| `view_counts.js` | `window.AGS_VIEW_COUNTS` | 記事URLごとの閲覧数 |
| `pillar_audit.js` | `window.AGS_PILLAR_AUDIT` | ピラー記事の検証結果 |
| `rewrite_candidates.js` | `window.AGS_REWRITE_CANDIDATES` | 書き直し提案（ERP の Viết lại と同じ 4 ルール＋重複）。非公開リポジトリ `ags-blogger-content` の週次点検が生成して置く |

これらのファイル名とデータ名は呼出元との接続仕様です。ファイル名、データ名、項目形式、Pages/CDN/rawのURLを変える場合は、Squarespace、Blogger、ERP等の利用先を確認して切り替えます。

生成ファイルは原則として直接編集せず、生成処理と入力条件を修正します。

## 生成処理

| 処理 | 入力設定 | 出力 | 現在の定期workflow |
| --- | --- | --- | --- |
| `scripts/update_word_counts.py` | `BLOGGER_API_KEY`, `BLOGGER_BLOG_ID` | `word_counts.js` | 対象 |
| `scripts/update_view_counts.py` | `GA4_PROPERTY_ID`, `GA4_SERVICE_ACCOUNT_JSON` | `view_counts.js` | 対象 |
| `scripts/pillar_audit.py` | Blogger設定、`word_counts.js` | `pillar_audit.js` | 現行のdaily workflowには含まれません |

`.github/workflows/main.yml` はscheduleと手動実行に対応します。閲覧数取得は失敗しても語数更新を継続する設定のため、workflow全体のsuccessだけで全データが更新されたとは判断しません。各ステップ結果と生成ファイルの更新日時を確認します。

## 情報と担当の境界

公開対象は公開サイトに使うデータです。APIキー、OAuthトークン、サービスアカウント秘密鍵、顧客・社員の生データは保存対象にしません。実際の認証値はGitHub ActionsのSecrets等で管理します。既存コードの設定方法の改善は、公開URL維持と分けて影響を確認します。

Codexは公開UIとデータの生成・配信を担当します。ERP GAS・Hub GAS内の認証、業務データ処理、APIバックエンドはClaude側の担当です。公開UIからGAS APIを利用する場合は、両者で接続仕様を合わせます。

## 名前を変更する場合

GitHubの通常のリポジトリURLの転送と、GitHub Pagesの配信URLは同じ扱いではありません。現在の公開URLを利用する画面・スクリプトの棚卸し、互換性確認、切替・復元手順が揃うまでは公開slugを維持します。

