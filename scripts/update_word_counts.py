#!/usr/bin/env python3
"""
Blogger word count updater for AGS blog (ketoan.ags-vina.com)
v2 — リトライ付き、部分結果保存、503対策
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser

# ============================================================
# 設定
# ============================================================
API_KEY = os.environ.get("BLOGGER_API_KEY", "AIzaSyBq3LO2ptxD40GaX853awXM2Dj9WR1vQy4")
BLOG_ID = os.environ.get("BLOGGER_BLOG_ID", "602305327945510887")
MAX_RESULTS = 150  # 1ページあたり (500→150に縮小してAPI負荷軽減)
BASE_URL = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts"
MAX_RETRIES = 5    # 503等のリトライ回数
RETRY_WAIT = 3     # リトライ初回待機秒
MIN_POSTS_TO_SAVE = 1000  # 最低この件数あれば部分保存する

# ============================================================
# HTMLからテキスト抽出
# ============================================================
class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)

    def get_text(self):
        return " ".join(self._text)


def html_to_text(html_content):
    extractor = HTMLTextExtractor()
    try:
        extractor.feed(html_content)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html_content)
    return extractor.get_text()


def count_words(text):
    if not text or not text.strip():
        return 0
    cjk_pattern = re.compile(
        r"[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff"
        r"\u4e00-\u9faf\u3400-\u4dbf\uf900-\ufaff]"
    )
    cjk_chars = len(cjk_pattern.findall(text))
    non_cjk = cjk_pattern.sub(" ", text)
    words = [w for w in non_cjk.split() if len(w) > 0]
    return len(words) + cjk_chars


# ============================================================
# API呼び出し (リトライ付き)
# ============================================================
def api_call_with_retry(request_url, page_num):
    """APIを呼び出し、503/429/500はリトライする"""
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(request_url)
            req.add_header("User-Agent", "AGS-BlogData-WordCounter/2.0")
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)

        except urllib.error.HTTPError as e:
            wait = RETRY_WAIT * (2 ** attempt)

            if e.code in (429, 500, 503):
                print(f"  ⚠ Page {page_num}: HTTP {e.code} (attempt {attempt+1}/{MAX_RETRIES}), {wait}秒待機...")
                time.sleep(wait)
                continue
            else:
                # 403等は即座にエラー内容を表示
                try:
                    err_body = json.loads(e.read().decode())
                    print(f"  ❌ Page {page_num}: HTTP {e.code}")
                    print(json.dumps(err_body, indent=2, ensure_ascii=False))
                except Exception:
                    print(f"  ❌ Page {page_num}: HTTP {e.code}: {e.reason}")
                return None

        except Exception as e:
            wait = RETRY_WAIT * (2 ** attempt)
            print(f"  ⚠ Page {page_num}: {type(e).__name__}: {e} (attempt {attempt+1}/{MAX_RETRIES}), {wait}秒待機...")
            time.sleep(wait)
            continue

    print(f"  ❌ Page {page_num}: {MAX_RETRIES}回リトライ失敗")
    return None


# ============================================================
# 全記事取得
# ============================================================
def fetch_all_posts():
    url_to_words = {}
    page_token = None
    page_num = 0
    consecutive_errors = 0

    while True:
        page_num += 1

        params = {
            "key": API_KEY,
            "maxResults": str(MAX_RESULTS),
            "fields": "nextPageToken,items(url,content)",
            "status": "LIVE",
            "fetchBodies": "true",
        }
        if page_token:
            params["pageToken"] = page_token

        request_url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"

        data = api_call_with_retry(request_url, page_num)

        if data is None:
            consecutive_errors += 1
            if page_num == 1:
                print("❌ 最初のページで失敗。APIキーまたはBlog IDを確認してください。")
                print(f"   API_KEY: {API_KEY[:10]}...{API_KEY[-4:]}")
                print(f"   BLOG_ID: {BLOG_ID}")
                return {}
            if consecutive_errors >= 3:
                print(f"  ⚠ 連続{consecutive_errors}回失敗。取得済み{len(url_to_words)}件で打ち切ります。")
                break
            # 1回失敗しても次のページトークンがないので停止
            print(f"  ⚠ Page {page_num} 失敗。取得済み{len(url_to_words)}件で打ち切ります。")
            break

        consecutive_errors = 0
        items = data.get("items", [])

        for post in items:
            url = post.get("url", "")
            content = post.get("content", "")
            if url:
                text = html_to_text(content)
                wc = count_words(text)
                url_to_words[url] = wc

        print(f"  📄 Page {page_num}: {len(items)}件 (累計 {len(url_to_words)}件)")

        page_token = data.get("nextPageToken")
        if not page_token:
            break

        # API rate limit 対策 — ページ間に少し間隔を空ける
        time.sleep(0.5)

    return url_to_words


# ============================================================
# word_counts.js に書き出す
# ============================================================
def write_word_counts_js(url_to_words):
    output_path = "word_counts.js"
    sorted_data = dict(sorted(url_to_words.items()))

    js_content = f"// Auto-generated by update_word_counts.py\n"
    js_content += f"// Updated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
    js_content += f"// Total posts: {len(sorted_data)}\n"
    js_content += f"var AGS_WORD_COUNTS = {json.dumps(sorted_data, ensure_ascii=False, indent=None)};\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"\n📝 {output_path} に書き出しました ({len(sorted_data):,}件)")


# ============================================================
# サマリー出力
# ============================================================
def print_summary(url_to_words):
    word_list = sorted(url_to_words.values())
    if not word_list:
        return

    print(f"\n📊 統計:")
    print(f"   記事数: {len(word_list):,}")
    print(f"   最大: {max(word_list):,} 語")
    print(f"   最小: {min(word_list):,} 語")
    print(f"   平均: {sum(word_list)/len(word_list):.0f} 語")
    print(f"   中央: {word_list[len(word_list)//2]:,} 語")

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
# メイン
# ============================================================
if __name__ == "__main__":
    print(f"🚀 AGS Blog Word Counter v2")
    print(f"   Blog ID: {BLOG_ID}")
    print(f"   API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
    print(f"   1ページあたり: {MAX_RESULTS}件")
    print(f"   リトライ: 最大{MAX_RETRIES}回 (初回{RETRY_WAIT}秒待機)")
    print()

    start = time.time()

    url_to_words = fetch_all_posts()

    if not url_to_words:
        print("❌ 取得結果が空です")
        sys.exit(1)

    total = len(url_to_words)
    elapsed = time.time() - start

    # 部分的な結果でも十分な件数なら保存する
    if total < MIN_POSTS_TO_SAVE:
        print(f"❌ 取得件数が{total}件 (最低{MIN_POSTS_TO_SAVE}件必要)。保存しません。")
        sys.exit(1)

    print(f"\n✅ 取得完了: {total:,}件 / {elapsed:.1f}秒")

    print_summary(url_to_words)
    write_word_counts_js(url_to_words)

    print()
    print(f"⏱  総時間: {elapsed:.1f}秒")
    print("✨ 完了!")
