import os
import json
import time
import requests
import re
import pandas as pd
import gspread
import urllib3
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- 初期設定 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# GitHub Secretsから読み込み
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
GOOGLE_JSON_DATA = os.environ.get('GOOGLE_JSON_DATA')

def main():
    print("🚀 処理開始...")
    
    # 1. スプレッドシートから「リモコン（B1セル）」の値を読み込む
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(GOOGLE_JSON_DATA)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # スプレッドシート名を確認（ご自身のシート名に合わせてください）
    spreadsheet_name = "YouTube分析シート"
    sheet = client.open(spreadsheet_name).sheet1
    
    # B1セルの検索ワードを取得
    search_keyword = sheet.acell('B1').value
    if not search_keyword:
        print("B1セルに検索ワードがありません。終了します。")
        return
    print(f"🔍 検索キーワード: {search_keyword}")

    # 2. ユーチュラでキーワード検索（スクレイピング）
    # 検索結果ページを直接叩く形にカスタマイズ
    search_url = f"https://yutura.net/ranking/?q={search_keyword}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(search_url, headers=headers, verify=False)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    uc_ids = []
    print("🆔 YouTube IDを抽出中...")
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if '/channel/' in href and 'channel' not in a.text:
            # 詳細ページからUC-IDを抜き出す
            try:
                detail_res = requests.get("https://yutura.net" + href, headers=headers, verify=False)
                match = re.search(r'youtube\.com/channel/(UC[\w-]+)', detail_res.text)
                if match:
                    uc_ids.append(match.group(1))
                time.sleep(0.5) # 負荷軽減
            except:
                continue
        if len(uc_ids) >= 15: break # まずは上位15件

    # --- 3. YouTube APIで詳細調査 ---
    if not uc_ids:
        print("❌ YouTube IDが1つも見つかりませんでした。B1セルのキーワードを変えてみてください。")
        return # IDがない場合はここで安全に終了させる

    print(f"📊 2. YouTube APIで詳細データを取得中 ({len(uc_ids)}件)...")
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    
    try:
        ch_res = youtube.channels().list(id=','.join(uc_ids), part='snippet,statistics').execute()
        
        # APIの返却結果に 'items' があるか確認
        if 'items' not in ch_res or not ch_res['items']:
            print("⚠️ APIから有効なデータが返ってきませんでした。")
            return

        new_data = []
        for item in ch_res['items']:
            # ...（以下、データの整理と書き出し処理）
            stats = item['statistics']
            new_data.append({
            "日付": datetime.now().strftime('%Y-%m-%d'),
            "名前": item['snippet']['title'],
            "登録者数": int(stats.get('subscriberCount', 0)),
            "総再生数": int(stats.get('viewCount', 0)),
            "動画数": int(stats.get('videoCount', 0)),
            "URL": f"https://www.youtube.com/channel/{item['id']}"
        })
    
    df_new = pd.DataFrame(new_data)

    # 4. 異変検知（前回データとの比較）
    # 前回のデータ（3行目以降に溜まっていると仮定）を読み込んで比較するロジック
    # 今回はシンプルに、最新の結果を「A3」セルから下に書き出します。
    # (B1が入力、A3から結果表という構成)
    
    print("📝 スプレッドシートへ書き出し中...")
    # ヘッダーとデータをリスト化
    output_list = [df_new.columns.values.tolist()] + df_new.values.tolist()
    
    # A3セルから結果を上書き
    # sheet.update('A3', output_list) は最新のgspreadでは以下のように書きます
    sheet.update(range_name='A3', values=output_list)
    
    print(f"✅ 完了！'{search_keyword}' の調査結果をシートに反映しました。")

if __name__ == "__main__":
    main()
