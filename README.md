# QuantScope TW v0.3（免費 API 試用版）

**狀態：可部署的專案程式碼，尚未接入你的私密金鑰，也尚未公開上線。**

## 免費方案限制

此版使用 Fugle `/intraday/quote/{symbol}`，只掃描 `WATCH_SYMBOLS` 指定的最多 5 檔股票，不是全市場自動選股。後端每 15 秒輪詢最多 5 個 HTTP 請求；實際可用性由 API 方案、網路、交易時段及資料授權決定。欲每天自動由全部上市上櫃股票挑出 5–10 檔，需要合規的盤前選股來源或升級付費快照服務。

## 在雲端服務部署（需支援 Python 長駐服務）

1. GitHub 建立私有 repository `quantscope-tw`，把本資料夾內檔案上傳到 repo 根目錄。
2. 選擇提供 Python Web Service 的雲端託管服務，以 GitHub repo 作為部署來源。
3. Startup command: `python3 server.py`，服務需自動設定 `PORT`。
4. **僅在雲端供應商的私密環境變數面板**設定：
   - `FUGLE_API_KEY`：富果金鑰（不得貼到對話、HTML、GitHub repo）
   - `WATCH_SYMBOLS`：例如 `2330,2317,2454,2603,2881`（只是追蹤清單，不代表推薦）
   - `REFRESH_SECONDS`：`15`
5. 建議先使用雲端供應商的私有網址／身分驗證或其他存取控管；目前此示範後端沒有登入認證，不適合直接當作對外公開行情轉發服務。確認你的 Fugle 授權條款。
6. 開啟託管服務的 HTTPS 網址，狀態應由「未設定 API」變成「已連接行情」，若權限不足會顯示 HTTP 錯誤，不會偽造資料。

**注意：GitHub Pages 只部署前端，無法執行 `server.py` 或保管金鑰。** 此版讓同一個雲端 Python Web Service 同時提供頁面與 API，是最簡單的路徑。

## 風險

此程式只做資料觀察與規則評分，不自動下單，也不是勝率模型。未匯入當日合法當沖股票清單時，標記為「資格未驗證」。停損止盈未校正股價升降單位、成本和滑價，不能直接下單。

## 文件

- https://developer.fugle.tw/docs/data/http-api/intraday/quote/
- https://developer.fugle.tw/docs/pricing/
