"""
自動リサーチbot(日次)

毎日、以下の3テーマを軽く調べて、Discordに通知＋リポジトリにログ保存する。
- AIツールの新製品
- 副業アイデアのネタ
- AI×プログラミングの組み合わせ

週次(weekly_research.py)では、この日次ログ7日分をもとに、
もっと深掘りしたレポートを作る。

必要な環境変数(GitHub Actionsの「Secrets」に設定します):
- GEMINI_API_KEY
- DISCORD_WEBHOOK_URL
"""

import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

import feedparser
import requests

JST = timezone(timedelta(hours=9))
GEMINI_MODEL = "gemini-3.5-flash"
MAX_PER_FEED = 8


def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ja&gl=JP&ceid=JP:ja"


SOURCES = {
    "AIツールの新製品": google_news_url("AI ツール 新機能 OR 新サービス OR リリース"),
    "副業アイデアのネタ": google_news_url("副業 OR 個人開発 OR 収益化 アイデア"),
    "AI×プログラミングの組み合わせ": "https://hnrss.org/frontpage",  # Hacker News(英語、AI開発者に人気の話題源)
}


def get_articles() -> dict:
    result = {}
    for label, url in SOURCES.items():
        feed = feedparser.parse(url)
        titles = [entry.title for entry in feed.entries[:MAX_PER_FEED]]
        result[label] = titles
    return result


def build_prompt(articles: dict, date_str: str) -> str:
    blocks = []
    for label, titles in articles.items():
        joined = "\n".join(f"- {t}" for t in titles) or "(取得できませんでした)"
        blocks.append(f"■{label}\n{joined}")
    source_text = "\n\n".join(blocks)

    return (
        f"あなたは個人開発者向けのリサーチャーです。{date_str}時点の以下の情報(海外情報を含む)をもとに、"
        "日本語で『今日の自動リサーチ』を作成してください。\n\n"
        "出力形式(Markdown、この構成を厳守):\n"
        "## AIツールの新製品\n"
        "(2〜3個、箇条書き。英語の情報も日本語で分かりやすく)\n\n"
        "## 副業アイデアのネタ\n"
        "(2〜3個、箇条書き。ニュースから読み取れる需要や機会を具体的に)\n\n"
        "## AI×プログラミングの動き\n"
        "(2〜3個、箇条書き。技術トレンドを分かりやすく)\n\n"
        "前置き・締めの挨拶は不要。この3見出し以外は出力しないこと。\n\n"
        f"{source_text}"
    )


def call_gemini(prompt: str, api_key: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Geminiの応答を解析できませんでした: {data}") from exc


def save_log(date_str: str, content: str) -> str:
    os.makedirs("data", exist_ok=True)
    path = f"data/{date_str}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 自動リサーチ {date_str}\n\n{content}\n")
    return path


def send_to_discord(date_str: str, content: str, webhook_url: str) -> None:
    message = f"🔬 **今日の自動リサーチ {date_str}**\n\n{content}"
    chunks = [message[i:i + 1900] for i in range(0, len(message), 1900)] or [message]
    for chunk in chunks:
        response = requests.post(webhook_url, json={"content": chunk}, timeout=30)
        response.raise_for_status()


def main() -> None:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    if not gemini_key or not discord_webhook:
        print("環境変数 GEMINI_API_KEY / DISCORD_WEBHOOK_URL が設定されていません", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now(JST).strftime("%Y-%m-%d")
    articles = get_articles()
    prompt = build_prompt(articles, date_str)
    content = call_gemini(prompt, gemini_key)

    path = save_log(date_str, content)
    print(f"ログを保存しました: {path}")

    send_to_discord(date_str, content, discord_webhook)
    print("Discordへの送信が完了しました")


if __name__ == "__main__":
    main()
