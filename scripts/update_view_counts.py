#!/usr/bin/env python3
# ============================================================
# AGS 閲覧数集計スクリプト (GitHub Actions用)
# ============================================================
# GA4 Data API から記事 URL 別の閲覧数 (screenPageViews) を取得し、
# view_counts.js を生成する。
#
# 環境変数:
#   GA4_PROPERTY_ID            - GA4 プロパティ ID (9桁数字)
#   GA4_SERVICE_ACCOUNT_JSON   - Service Account JSON 全文
#
# 出力:
#   view_counts.js
#     window.AGS_VIEW_COUNTS = { "https://ketoan.ags-vina.com/...html": 12345, ... };
#
# 取得期間: 過去365日 (デフォルト) ※環境変数 GA4_LOOKBACK_DAYS で変更可
# ============================================================

import os
import sys
import json
import time

# ============================================================
# 設定
# ============================================================
PROPERTY_ID = os.environ.get('GA4_PROPERTY_ID', '').strip()
SA_JSON = os.environ.get('GA4_SERVICE_ACCOUNT_JSON', '').strip()
LOOKBACK_DAYS = int(os.environ.get('GA4_LOOKBACK_DAYS', '365'))
OUTPUT_FILE = 'view_counts.js'
SITE_HOST = 'ketoan.ags-vina.com'

if not PROPERTY_ID:
    print("❌ GA4_PROPERTY_ID environment variable not set")
    sys.exit(1)
if not SA_JSON:
    print("❌ GA4_SERVICE_ACCOUNT_JSON environment variable not set")
    sys.exit(1)


# ============================================================
# GA4 Data API 呼び出し
# ============================================================
def fetch_view_counts():
    """
    GA4 から pagePath 別の screenPageViews を取得。
    return: { "/2024/05/article.html": 12345, ... }
    """
    from google.oauth2 import service_account
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, Dimension, Metric, DateRange, OrderBy, Filter,
        FilterExpression, FilterExpressionList,
    )

    # Service Account 認証
    sa_info = json.loads(SA_JSON)
    credentials = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=['https://www.googleapis.com/auth/analytics.readonly']
    )
    client = BetaAnalyticsDataClient(credentials=credentials)

    print(f"📊 GA4 Property: {PROPERTY_ID}")
    print(f"📅 Lookback: {LOOKBACK_DAYS} days")
    print(f"🔍 Host filter: {SITE_HOST}")
    print()

    # ページネーション対応 (1回のクエリで最大 100,000 行、limit=100000 を使う)
    all_rows = {}
    offset = 0
    page_size = 100000

    while True:
        req = RunReportRequest(
            property=f"properties/{PROPERTY_ID}",
            dimensions=[Dimension(name="pagePath")],
            metrics=[Metric(name="screenPageViews")],
            date_ranges=[DateRange(start_date=f"{LOOKBACK_DAYS}daysAgo", end_date="today")],
            dimension_filter=FilterExpression(
                filter=Filter(
                    field_name="hostName",
                    string_filter=Filter.StringFilter(
                        match_type=Filter.StringFilter.MatchType.EXACT,
                        value=SITE_HOST
                    )
                )
            ),
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
            limit=page_size,
            offset=offset,
        )
        response = client.run_report(req)

        rows = response.rows
        for row in rows:
            path = row.dimension_values[0].value
            views = int(row.metric_values[0].value)
            # pagePath は "/2024/05/article.html" の形式 → URL に変換
            if not path.startswith('/'):
                path = '/' + path
            # クエリ文字列を除去 (?m=1 等の Blogger モバイル判定パラメータ)
            path = path.split('?')[0].split('#')[0]
            url = f"https://{SITE_HOST}{path}"
            # 同じ URL に複数 path がマージされる場合 (例: ?m=0 と ?m=1) は加算
            all_rows[url] = all_rows.get(url, 0) + views

        print(f"  ページ取得: {len(rows)} 行 (累計 URL 数: {len(all_rows)})")

        if len(rows) < page_size:
            break
        offset += page_size

    return all_rows


# ============================================================
# 記事 URL のみフィルタ (固定ページ、トップ、ラベルページ等を除外)
# ============================================================
def is_article_url(url):
    """記事URLか判定 (/YYYY/MM/slug.html のみ)"""
    import re
    if '/p/' in url:        # 固定ページ
        return False
    if '/search/' in url:   # ラベル/検索
        return False
    if not url.rstrip('/').endswith('.html'):
        return False
    if not re.search(r'/20\d{2}/\d{2}/', url):
        return False
    return True


# ============================================================
# view_counts.js 生成
# ============================================================
def write_view_counts_js(view_data):
    """view_counts.js を生成"""
    from datetime import datetime, timezone, timedelta
    ict = timezone(timedelta(hours=7))
    now = datetime.now(ict).strftime("%Y-%m-%d %H:%M:%S")

    # 記事 URL のみ残す
    filtered = {url: cnt for url, cnt in view_data.items() if is_article_url(url)}

    # views 降順でソート (人気記事が先頭)
    sorted_items = sorted(filtered.items(), key=lambda x: -x[1])
    out = {url: cnt for url, cnt in sorted_items}

    total_views = sum(out.values())

    content = (
        "// AGS Blog 閲覧数データ (GA4)\n"
        f"// 自動生成: GitHub Actions ({now} ICT)\n"
        f"// 期間: 過去 {LOOKBACK_DAYS} 日間\n"
        f"// 記事数: {len(out):,} 件 / 合計閲覧数: {total_views:,}\n"
        "//\n"
        "// このファイルは GitHub Actions で毎日自動更新されます。\n"
        "// 手動編集しないでください。\n"
        "\n"
        "window.AGS_VIEW_COUNTS = " +
        json.dumps(out, ensure_ascii=False, indent=0) +
        ";\n"
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    size = os.path.getsize(OUTPUT_FILE)
    print()
    print(f"📦 ファイル生成: {OUTPUT_FILE}")
    print(f"   サイズ: {size:,} bytes ({size/1024:.1f} KB)")
    print(f"   記事数: {len(out):,}")
    print(f"   合計閲覧数: {total_views:,}")

    # 上位10件を表示
    print()
    print("🏆 閲覧数 TOP 10:")
    for i, (url, views) in enumerate(sorted_items[:10], 1):
        slug = url.split('/')[-1].replace('.html', '')[:50]
        print(f"   {i:2d}. {views:>8,} views | {slug}")


# ============================================================
# 実行
# ============================================================
if __name__ == "__main__":
    start = time.time()

    print("=" * 60)
    print("👁  GA4 閲覧数集計開始")
    print("=" * 60)

    try:
        view_data = fetch_view_counts()
    except Exception as e:
        print(f"\n❌ GA4 API エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if not view_data:
        print("⚠️ 閲覧データが空でした (GA4 にデータがない可能性)")
        sys.exit(0)

    write_view_counts_js(view_data)

    print()
    print(f"⏱  総時間: {time.time() - start:.1f}秒")
    print("✨ 完了!")
