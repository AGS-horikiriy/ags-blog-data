#!/usr/bin/env python3
# ============================================================
# AGS Blogger 語数自動取得スクリプト (GitHub Actions用)
# ============================================================
# Bloggerから全公開記事の語数を取得し、word_counts.js を生成する。
# GitHub Actions のスケジュール実行で毎日自動更新される。
#
# 環境変数:
#   BLOGGER_API_KEY  - Blogger API キー (GitHub Secrets で設定)
#   BLOGGER_BLOG_ID  - ブログ ID (GitHub Secrets で設定)
#
# 出力:
#   word_counts.js   - リポジトリのルートに生成
# ============================================================

import os
import sys
import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error

# ============================================================
# 設定 (環境変数から取得)
# ============================================================
API_KEY = os.environ.get('BLOGGER_API_KEY', '').strip()
BLOG_ID = os.environ.get('BLOGGER_BLOG_ID', '').strip()
OUTPUT_FILE = 'word_counts.js'

if not API_KEY:
    print("❌ BLOGGER_API_KEY environment variable not set")
    sys.exit(1)
if not BLOG_ID:
    print("❌ BLOGGER_BLOG_ID environment variable not set")
    sys.exit(1)

# ============================================================
# HTML→プレーンテキスト
# ============================================================
def html_to_plain_text(html):
    """
    カット規則:
    1. <h2>...Thông tin khác...</h2> 以降を全カット
    2. <blockquote>の中身は除外
    3. HTMLタグ全般を削除
    """
    if not html:
        return ""
    text = html
    
    # ルール1: Thông tin khác のH2以降カット
    cut_pattern = re.compile(
        r'<h2[^>]*>(?:(?!</h2>).)*?th[oôốơ]ng\s*tin\s*kh[aáà]c(?:(?!</h2>).)*?</h2>',
        re.IGNORECASE | re.DOTALL
    )
    match = cut_pattern.search(text)
    if match:
        text = text[:match.start()]
    
    # ルール2: blockquote 除外
    text = re.sub(r'<blockquote[\s\S]*?</blockquote>', '', text, flags=re.IGNORECASE)
    
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|h[1-6]|li|tr)>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    entities = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
                "&quot;": '"', "&#39;": "'", "&apos;": "'"}
    for k, v in entities.items():
        text = text.replace(k, v)
    text = re.sub(r"&[a-zA-Z]+;", "", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"[\s\n\r]+", " ", text).strip()
    return text


def count_words(text):
    """単語数をカウント (スペース区切り)"""
    if not text:
        return 0
    normalized = re.sub(r'\s+', ' ', text.strip())
    if not normalized:
        return 0
    words = normalized.split(' ')
    words = [w for w in words if w and re.search(r'\w', w, re.UNICODE)]
    return len(words)


# ============================================================
# Blogger API から全記事取得
# ============================================================
def fetch_all_posts():
    """全公開記事の URL→語数 マッピングを取得"""
    url_to_words = {}
    page_token = ""
    page_num = 0
    
    print("=" * 60)
    print(f"🚀 Blogger 取得開始")
    print(f"   BLOG_ID: {BLOG_ID}")
    print("=" * 60)

    while True:
        page_num += 1
        params = {
            "key": API_KEY,
            "maxResults": 500,
            "status": "live",
            "fetchBodies": "true",
            "fields": "nextPageToken,items(url,content)",
        }
        if page_token:
            params["pageToken"] = page_token
        url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts?{urllib.parse.urlencode(params)}"

        page_start = time.time()
        print(f"📄 ページ {page_num}... (累計 {len(url_to_words)})", end=" ", flush=True)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ags-github-actions/1.0"})
            with urllib.request.urlopen(req, timeout=60) as res:
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"\n❌ HTTPエラー {e.code}: {body[:300]}")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ エラー: {e}")
            sys.exit(1)

        items = data.get("items", []) or []
        for post in items:
            post_url = post.get("url", "")
            html = post.get("content", "") or ""
            if post_url:
                plain = html_to_plain_text(html)
                url_to_words[post_url] = count_words(plain)

        print(f"✓ {len(items)}件 ({time.time()-page_start:.1f}秒)")
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
        time.sleep(0.3)

    return url_to_words


# ============================================================
# word_counts.js 生成
# ============================================================
def write_word_counts_js(url_to_words):
    """word_counts.js を生成"""
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=7))  # Vietnam time
    now = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")
    
    content = f"""// AGS Blog 語数データ
// 自動生成: GitHub Actions ({now} ICT)
// データ件数: {len(url_to_words):,} 件
//
// このファイルは GitHub Actions で毎日自動更新されます。
// 手動編集しないでください。

window.AGS_WORD_COUNTS = {json.dumps(url_to_words, ensure_ascii=False, sort_keys=True, indent=0)};
"""
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    
    size_bytes = os.path.getsize(OUTPUT_FILE)
    print()
    print(f"📦 ファイル生成: {OUTPUT_FILE}")
    print(f"   サイズ: {size_bytes:,} bytes ({size_bytes/1024:.1f} KB)")
    print(f"   件数:   {len(url_to_words):,} 件")


# ============================================================
# サマリー
# ============================================================
def print_summary(url_to_words):
    if not url_to_words:
        return
    
    word_list = sorted(url_to_words.values())
    print()
    print("📊 統計")
    print(f"   最大: {max(word_list):,} 語")
    print(f"   最小: {min(word_list):,} 語")
    print(f"   平均: {sum(word_list)/len(word_list):.0f} 語")
    print(f"   中央: {word_list[len(word_list)//2]:,} 語")
    
    # 語数分布
    print()
    print("   📊 分布:")
    buckets = [
        ("    0- 799 (リライト候補)",  0,  800),
        ("  800-1999 (標準未満)",   800, 2000),
        (" 2000-4999 (標準)",      2000, 5000),
        (" 5000+    (大作)",       5000, float("inf")),
    ]
    for label, lo, hi in buckets:
        count = sum(1 for w in word_list if lo <= w < hi)
        pct = count / len(word_list) * 100 if word_list else 0
        print(f"      {label:<32s} {count:>5,} 件 ({pct:>4.1f}%)")


# ============================================================
# 実行
# ============================================================
if __name__ == "__main__":
    start = time.time()
    
    url_to_words = fetch_all_posts()
    
    if not url_to_words:
        print("❌ 取得結果が空です")
        sys.exit(1)
    
    print(f"\n✅ 取得完了: {len(url_to_words):,}件 / {time.time()-start:.1f}秒")
    
    print_summary(url_to_words)
    write_word_counts_js(url_to_words)
    
    print()
    print(f"⏱  総時間: {time.time()-start:.1f}秒")
    print("✨ 完了!")
