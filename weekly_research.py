"""
自動リサーチbot(週次・深掘り版)

直近7日分の日次リサーチログを読み込み、Geminiにもっと踏み込んだ
分析(繰り返し出てきたテーマ、事業化できそうな仮説など)をさせて
Discordに通知する。

必要な環境変数(GitHub Actionsの「Secrets」に設定します、日次と同じものでOK):
- GEMINI_API_KEY
- DISCORD_WEBHOOK_URL
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import requests

JST = timezone(timedelta(hours=9))
GEMINI_MODEL = "gemini-3.5-flash"
DAYS_TO_LOOK_BACK = 7


def load_recent_logs() -> list[str]:
    today = datetime.now(JST).date()
    contents = []
    for i in range(DAYS_TO_LOOK_BACK):
        day = today - timedelta(days=i)
        path = f"data/{day.isoformat()}.md"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                contents.append(f.read())
    return contents


def summarize_week(logs: list[str], api_key: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    joined = "\n\n---\n\n".join(logs)

    prompt = (
        "あなたは個人開発者の相談役です。以下は、この1週間分の日次自動リサーチのログです"
        "(AIツールの新製品／副業アイデア／AI×プログラミングの3テーマ)。"
        "これを踏まえて『週次の深掘りリサーチレポート』を作成してください。\n\n"
        "出力形式(Markdown、この構成を厳守):\n"
        "## 今週のAIツール動向まとめ\n"
        "(繰り返し出てきた流れや、注目すべき製品・機能を整理。2〜4個)\n\n"
        "## 副業・個人開発のチャンス仮説\n"
        "(今週の情報から見えてきた『これはやれそう』という仮説を、実現方法のヒント付きで2〜3個。"
        "できるだけ具体的に、初期費用ゼロ〜低コストで始められる方向性を意識する)\n\n"
        "## AI×プログラミングで押さえておきたい動き\n"
        "(技術トレンドの整理。2〜3個)\n\n"
        "## 来週の注目ポイント\n"
        "(来週も引き続きウォッチすべきことを1〜2個)\n\n"
        "前置き・締めの挨拶は不要。この4見出し以外は出力しないこと。\n\n"
        f"{joined}"
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Geminiの応答を解析できませんでした: {data}") from exc


def send_to_discord(message: str, webhook_url: str) -> None:
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

    logs = load_recent_logs()
    if not logs:
        print("直近のログが見つかりませんでした。data/ フォルダを確認してください。", file=sys.stderr)
        sys.exit(1)

    summary = summarize_week(logs, gemini_key)
    message = f"🗓️ **週次・深掘りリサーチレポート**\n\n{summary}"
    send_to_discord(message, discord_webhook)
    print("週次レポートをDiscordへ送信しました")


if __name__ == "__main__":
    main()
