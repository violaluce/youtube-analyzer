import os
import json
import time
import requests
import re
import pandas as pd
import gspread
import urllib3
import isodate
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- 初期設定 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# GitHub Secretsから環境変数を読み込む
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
GOOGLE_JSON_DATA = os.environ.get('GOOGLE_JSON_DATA')

def get_yutura_list():
    """ユーチュラのランキングからチャンネルURLを取得"""
    # 2026年2月の再生回数ランキング
    url = "https://yutura.net/ranking/mon/?mode=view&date=202602&p=1"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        
        channels = []
        for a in soup.find_all('a'):
            href = a.get('href', '')
            # チャンネル個別ページへのリンクを抽出
            if '/channel/' in href and a.text.strip() and 'チャンネルの詳細' not in a.text:
                channels.append({"name": a.text.strip(), "url": "https://yutura.net" + href})
        
        # 重複削除
        unique_channels = []
        seen = set()
        for c in channels:
            if c['url'] not in seen:
                unique_channels.append(c)
                seen.add(c['url'])
        return unique_channels
    except Exception as e:
        print(f"ユーチュラ取得エラー: {e}")
        return []

def get_yt_id(yutura_url):
    """ユーチュラ詳細ページからYouTube ID (UC...) を抽出"""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(yutura_url, headers=headers, verify=False, timeout=10)
        match = re.search(r'youtube\.com/channel/(UC[\w-]+)', res.text)
        return match.group(1) if match else None
    except:
        return None

def main():
    print("🚀 1. ユーチュラからリストを取得中...")
    raw_list = get_yutura_list()
    
    if not raw_list:
        print("リストが取得できませんでした。終了します。")
        return

    print(f"   {len(raw_list)}件の候補を発見。YouTube IDを特定中...")
    
    data_for_api = []
    # API節約のため、まずはIDを特定（上位20件程度でテスト）
    for item in raw_list[:20]:
        uid = get_yt_id(item['url'])
        if uid:
            data_for_api.append(uid)
        time.sleep(1) # サイトへの負荷軽減

    print(f"📊 2. YouTube APIで詳細データを取得中 ({len(data_for_api)}件)...")
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    
    # まとめて取得（最大50件まで1通信）
    ch_res = youtube.channels().list(
        id=','.join(data_for_api),
        part='snippet,statistics'
    ).execute()

    final_data = []
    for item in ch_res['items']:
        final_data.append({
            "日付": datetime.now().strftime('%Y-%m-%d'),
            "名前": item['snippet']['title'],
            "登録者数": int(item['statistics']['subscriberCount']),
            "総再生数": int(item['statistics']['viewCount']),
            "動画数": int(item['statistics']['videoCount']),
            "URL": f"https://www.youtube.com/channel/{item['id']}"
        })
    
    df_new = pd.DataFrame(final_data)

    print("📝 3. スプレッドシートへ書き込み中...")
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(GOOGLE_JSON_DATA)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # スプレッドシート名に合わせて変更してください
    sheet = client.open("YouTube分析シート").sheet1

    # B1セルに入力されたキーワードを取得する
    search_keyword = sheet.acell('B1').value
    print(f"スプレッドシートから取得したキーワード: {search_keyword}")

    # このキーワードを使って検索ロジックを回す
    # url = f"https://yutura.net/ranking/?q={search_keyword}" ...のような形
    
    # クリアして上書き（差分計算はシート側の関数でも対応可能）
    sheet.clear()
    header = [df_new.columns.values.tolist()]
    values = df_new.values.tolist()
    sheet.update('A1', header + values)
    
    print("✅ 全工程が完了しました！")

if __name__ == "__main__":
    main()
