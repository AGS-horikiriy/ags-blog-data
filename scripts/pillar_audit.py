#!/usr/bin/env python3
# ============================================================
# AGS ピラーポスト検証スクリプト (GitHub Actions用)
# ============================================================
# TỔNG HỢP ラベルの記事 (ピラーポスト) を取得し、
# 本文内の内部リンク (クラスター記事) を抽出。
# 各クラスター記事の語数を照合して pillar_audit.js を生成する。
#
# 環境変数:
#   BLOGGER_API_KEY  - Blogger API キー
#   BLOGGER_BLOG_ID  - ブログ ID
#
# 出力:
#   pillar_audit.js  - リポジトリのルートに生成
#
# 依存: word_counts.js (同じリポジトリ、語数データ)
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
# 設定
# ============================================================
API_KEY = os.environ.get('BLOGGER_API_KEY', '').strip()
BLOG_ID = os.environ.get('BLOGGER_BLOG_ID', '').strip()
OUTPUT_FILE = 'pillar_audit.js'
WORD_COUNTS_FILE = 'word_counts.js'

# 語数しきい値 (word_counts と同一)
T_REWRITE = 800
T_STANDARD = 2000
T_EXCELLENT = 5000

if not API_KEY:
    print("❌ BLOGGER_API_KEY environment variable not set")
    sys.exit(1)
if not BLOG_ID:
    print("❌ BLOGGER_BLOG_ID environment variable not set")
    sys.exit(1)


# ============================================================
# word_counts.js を読み込み (URL → 語数 マップ)
# ============================================================
def load_word_counts():
    """word_counts.js から window.AGS_WORD_COUNTS の JSON を抽出"""
    if not os.path.exists(WORD_COUNTS_FILE):
        print("⚠️  " + WORD_COUNTS_FILE + " が見つかりません。語数照合をスキップします。")
        return {}
    with open(WORD_COUNTS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    # window.AGS_WORD_COUNTS = {...}; から JSON 部分を抽出
    m = re.search(r'window\.AGS_WORD_COUNTS\s*=\s*(\{.*\})\s*;?\s*$', content, re.DOTALL)
    if not m:
        print("⚠️  word_counts.js のパースに失敗")
        return {}
    try:
        return json.loads(m.group(1))
    except Exception as e:
        print("⚠️  word_counts.js JSON パースエラー:", e)
        return {}


def get_word_count(word_counts, url):
    """URL から語数を取得 (末尾スラッシュ等のフォールバック付き)"""
    if not url:
        return None
    if url in word_counts:
        return word_counts[url]
    alt = url[:-1] if url.endswith('/') else url + '/'
    if alt in word_counts:
        return word_counts[alt]
    clean = url.split('?')[0].split('#')[0]
    if clean in word_counts:
        return word_counts[clean]
    return None


def get_word_level(words):
    """語数 → レベル分類"""
    if words is None:
        return 'unknown'
    if words <= T_REWRITE:
        return 'rewrite'
    if words < T_STANDARD:
        return 'low'
    if words < T_EXCELLENT:
        return 'good'
    return 'excellent'


# ============================================================
# ラベル分類
# ============================================================
def is_tonghop_label(label):
    """TỔNG HỢP ラベルか判定 (発音記号無視)"""
    if not label:
        return False
    n = str(label).lower().replace('đ', 'd').replace('Đ', 'd')
    # NFD 正規化で発音記号を除去
    import unicodedata
    n = ''.join(c for c in unicodedata.normalize('NFD', n)
                if unicodedata.category(c) != 'Mn')
    return n.startswith('tong hop')


# ============================================================
# 「Thông tin khác」以降をカット
# ============================================================
def cut_thong_tin_khac(html):
    """<h2>...Thông tin khác...</h2> 以降を削除"""
    cut = re.compile(
        r'<h2[^>]*>(?:(?!</h2>).)*?th[oôốơ]ng\s*tin\s*kh[aáà]c(?:(?!</h2>).)*?</h2>',
        re.IGNORECASE | re.DOTALL)
    m = cut.search(html)
    if m:
        return html[:m.start()]
    return html


# ============================================================
# 内部リンク (クラスター記事) 判定
# ============================================================
def is_cluster_link(url):
    """ketoan.ags-vina.com の記事ページURLか判定"""
    if 'ketoan.ags-vina.com' not in url:
        return False
    if '/p/' in url:           # 固定ページ
        return False
    if '/search/' in url:      # ラベルページ
        return False
    if not url.rstrip('/').endswith('.html'):
        return False
    if not re.search(r'/20\d{2}/\d{2}/', url):  # /YYYY/MM/ 記事パターン
        return False
    return True


def extract_cluster_links(html):
    """本文HTMLからクラスター記事リンクを抽出 (重複除去、順序保持)"""
    links = []
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        url = m.group(1).strip()
        # HTMLエンティティのデコード
        url = url.replace('&amp;', '&')
        if is_cluster_link(url):
            links.append(url)
    # 重複除去 (順序保持)
    return list(dict.fromkeys(links))


# ============================================================
# Blogger API: TỔNG HỢP記事を本文込みで取得
# ============================================================
def fetch_tonghop_posts():
    """TỔNG HỢPラベルの記事を本文込みで全件取得"""
    posts = []
    page_token = ""
    page_num = 0

    print("=" * 60)
    print("🏛 ピラーポスト (TỔNG HỢP) 取得開始")
    print("=" * 60)

    # label パラメータで TỔNG HỢP のみ取得
    label = 'TỔNG HỢP'

    while True:
        page_num += 1
        params = {
            "key": API_KEY,
            "maxResults": 50,
            "status": "live",
            "fetchBodies": "true",   # ★ 本文込み
            "labels": label,
            "fields": "nextPageToken,items(id,title,url,published,labels,content)",
        }
        if page_token:
            params["pageToken"] = page_token
        url = ('https://www.googleapis.com/blogger/v3/blogs/' + BLOG_ID +
               '/posts?' + urllib.parse.urlencode(params))

        print("📄 ページ " + str(page_num) + "... (累計 " + str(len(posts)) + ")",
              end=" ", flush=True)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ags-pillar-audit/1.0"})
            with urllib.request.urlopen(req, timeout=60) as res:
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print("\n❌ HTTPエラー " + str(e.code) + ": " + body[:300])
            sys.exit(1)
        except Exception as e:
            print("\n❌ エラー: " + str(e))
            sys.exit(1)

        items = data.get("items", []) or []
        posts.extend(items)
        print("✓ " + str(len(items)) + "件")

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
        time.sleep(0.3)

    return posts


# ============================================================
# ピラーポスト検証
# ============================================================
def audit_pillar(post, word_counts):
    """1つのピラーポストを検証して結果dictを返す"""
    content = post.get('content', '') or ''
    pillar_url = post.get('url', '')

    # ピラー記事自体の語数
    pillar_words = get_word_count(word_counts, pillar_url)

    # 本文を Thông tin khác でカット
    body = cut_thong_tin_khac(content)

    # クラスター記事リンク抽出
    links = extract_cluster_links(body)

    # 各リンクの語数を照合
    link_results = []
    summary = {'good': 0, 'low': 0, 'rewrite': 0, 'excellent': 0, 'unknown': 0}
    for link_url in links:
        w = get_word_count(word_counts, link_url)
        level = get_word_level(w)
        summary[level] += 1
        link_results.append({
            'url': link_url,
            'words': w,         # null の場合あり
            'level': level
        })

    return {
        'title': post.get('title', ''),
        'pillar_words': pillar_words,
        'published': post.get('published', ''),
        'link_count': len(links),
        'links': link_results,
        'summary': summary
    }


# ============================================================
# pillar_audit.js 生成
# ============================================================
def write_pillar_audit_js(audit_data):
    """pillar_audit.js を生成"""
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=7))  # Vietnam time
    now = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")

    content = (
        "// AGS ピラーポスト検証データ\n"
        "// 自動生成: GitHub Actions (" + now + " ICT)\n"
        "// ピラーポスト数: " + str(len(audit_data)) + " 件\n"
        "//\n"
        "// このファイルは GitHub Actions で毎日自動更新されます。\n"
        "// 手動編集しないでください。\n"
        "\n"
        "window.AGS_PILLAR_AUDIT = " +
        json.dumps(audit_data, ensure_ascii=False, sort_keys=True, indent=0) +
        ";\n"
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    size = os.path.getsize(OUTPUT_FILE)
    print()
    print("📦 ファイル生成: " + OUTPUT_FILE)
    print("   サイズ: {:,} bytes ({:.1f} KB)".format(size, size / 1024))
    print("   ピラーポスト数: " + str(len(audit_data)) + " 件")


# ============================================================
# サマリー表示
# ============================================================
def print_summary(audit_data):
    if not audit_data:
        return
    print()
    print("📊 検証サマリー")
    print("-" * 60)

    total_links = 0
    total_rewrite = 0
    total_unknown = 0
    pillars_with_issues = 0

    for url, data in audit_data.items():
        s = data['summary']
        total_links += data['link_count']
        total_rewrite += s['rewrite']
        total_unknown += s['unknown']
        if s['rewrite'] > 0:
            pillars_with_issues += 1

    print("  ピラーポスト総数:        {:>4} 件".format(len(audit_data)))
    print("  内部リンク総数:          {:>4} 本".format(total_links))
    print("  リライト候補リンク:      {:>4} 本".format(total_rewrite))
    print("  語数データなしリンク:    {:>4} 本".format(total_unknown))
    print("  要改善ピラー (🔴あり):   {:>4} 件".format(pillars_with_issues))

    # 要改善ピラーの上位
    issues = [(url, d) for url, d in audit_data.items() if d['summary']['rewrite'] > 0]
    issues.sort(key=lambda x: x[1]['summary']['rewrite'], reverse=True)
    if issues:
        print()
        print("  ⚠️ 要改善ピラー (リライト候補リンク数 上位):")
        for url, d in issues[:10]:
            print("     🔴{:>2}件  {}".format(
                d['summary']['rewrite'], d['title'][:45]))


# ============================================================
# 実行
# ============================================================
if __name__ == "__main__":
    start = time.time()

    # word_counts.js 読み込み
    word_counts = load_word_counts()
    print("📚 word_counts.js: " + str(len(word_counts)) + " 件の語数データ")
    print()

    # TỔNG HỢP記事取得
    posts = fetch_tonghop_posts()

    if not posts:
        print("❌ TỔNG HỢP記事が取得できませんでした")
        sys.exit(1)

    print()
    print("✅ ピラーポスト取得: " + str(len(posts)) + " 件 / "
          + "{:.1f}秒".format(time.time() - start))

    # 各ピラーを検証
    audit_data = {}
    for post in posts:
        url = post.get('url', '')
        if not url:
            continue
        audit_data[url] = audit_pillar(post, word_counts)

    # サマリー & 出力
    print_summary(audit_data)
    write_pillar_audit_js(audit_data)

    print()
    print("⏱  総時間: {:.1f}秒".format(time.time() - start))
    print("✨ 完了!")
