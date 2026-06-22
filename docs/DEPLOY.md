# 部署到雲端常駐主機（VPS + Docker）

把 dry-run bot 搬到一台**不會睡眠**的主機常駐，解決「本機睡眠 / 關機 bot 就停」的問題。
用 Docker Compose + freqtrade 官方 image，不需在 VPS 上裝 Python / TA-Lib。

> 仍是 **dry-run（模擬盤）**，不碰真錢，也不需要 OKX API key。
> 之後若要實盤，再依 `CLAUDE.md` 的實盤檢查清單調整。

---

## 最小部署 checklist（懶人包）

VPS 已裝好 Docker 的前提下，從零到 bot 常駐只要這幾步。每步細節見下方對應章節。

```bash
# 1. 取得程式碼（strategies / docker-compose.yml / Makefile 都在 git 裡）
git clone <你的 repo> freqtrade-okx && cd freqtrade-okx

# 2. 傳上唯一沒進 git 的機密設定（含 UI 帳密 / jwt_secret_key）
scp user_data/config.json <user>@<vps>:~/freqtrade-okx/user_data/config.json

# 3. ⚠️ 關鍵：官方 image 以 uid 1000 執行，要讓它能寫 user_data（否則 sqlite 寫不了、bot 報錯）
sudo chown -R 1000:1000 user_data

# 4. 啟動 dry-run bot
make up            # = docker compose up -d

# 5. 驗證
make ps            # 容器 Up？
make logs          # 有正常連上 OKX、無 permission error？
```

連 Web UI（見「五、連 Web UI」）：預設是公網 IP，需設**防火牆限 IP** + **config.json 加 CORS**
兩步才連得上且能登入；或改走 SSH tunnel（方法 B）不開公網。

**不需要做的事**：不用 `make download`（dry-run 會即時抓 K 線）、不用填 OKX API key（不下真單）、
不用改 config.json 的 listen_ip / port（已由 docker-compose 環境變數與 port mapping 處理）。

**公網部署前必做**：換掉 `config.json` 的 UI `username` / `password`（目前 `leon` / `aaaaa`）
與 `jwt_secret_key`。預設 port 只綁 `127.0.0.1` 走 tunnel 已相對安全，但換掉才保險。

> 前提（只需一次）：VPS 裝 Docker（`curl -fsSL https://get.docker.com | sh`）；
> 要用 `make` 指令需 `sudo apt install make`，沒裝就直接用 `docker compose up -d` / `ps` / `logs -f`。

---

## 為什麼不用 Cloudflare Worker

Worker 是「定時觸發、跑幾秒就結束」的短命無狀態模型（像 `line-daily-report`），
而 freqtrade 需要**常駐 Python 行程 + 原生 TA-Lib + 與交易所長連線 + 持久狀態**，
兩者本質不相容。長時間掛 bot 該用常駐主機 / 容器。
（不過「每日把績效推到 LINE」這種定時通知很適合做成 Worker，之後可另外加。）

---

## 一、準備一台 VPS

任何便宜的 Linux VPS 即可（Hetzner / Vultr / DigitalOcean，~$5/月，1 vCPU / 1GB RAM 夠跑 dry-run bot）。
作業系統選 Ubuntu 22.04/24.04 LTS。

裝 Docker：

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # 之後免 sudo，重新登入生效
```

## 二、把專案放上去

只需要這些檔案/目錄，**不要**上傳 `.venv`、歷史資料可不帶（dry-run 會即時抓）：

- `docker-compose.yml`
- `user_data/config.json`（**含機密，不在 git**，要手動 scp 上去）
- `user_data/strategies/`（`DonchianBreakout.py`）

最簡單做法 —— git clone 後補上 gitignored 的 config.json：

```bash
git clone <你的 repo> freqtrade-okx && cd freqtrade-okx
# 從本機把唯一沒進 git 的機密設定傳上去：
scp user_data/config.json  <user>@<vps-ip>:~/freqtrade-okx/user_data/config.json
```

> `config.json` 被 `.gitignore` 排除（含 `jwt_secret_key` 與 UI 帳密），所以一定要手動傳。
> 公網部署前**務必**換掉 config.json 裡的 `username` / `password` / `jwt_secret_key`（目前是練習用弱值）。

## 三、檔案權限

官方 image 以 uid 1000（`ftuser`）執行，需能讀寫掛載進去的 `user_data`：

```bash
sudo chown -R 1000:1000 user_data
```

## 四、啟動

```bash
docker compose up -d        # 背景常駐 bot
docker compose ps           # 看狀態
docker compose logs -f      # 看即時 log（Ctrl-C 只是離開 log，不會停 bot）
```

`restart: unless-stopped` 會在 VPS 重開機 / 容器崩潰時自動把 bot 拉回來。

## 五、連 Web UI

bot 的 Web UI 在 port 8080（DonchianBreakout），
帳密見 `config.json` 的 `api_server.username / password`。兩種連法擇一。

### 方法 A：公網 IP + 防火牆限 IP（目前 `docker-compose.yml` 預設）

compose 已把 port 發佈到 `0.0.0.0`（對外）。安全性靠**雲端防火牆只放行你的固定 IP**。
這是「網路層擋人」+「應用層 CORS」兩件事，**缺一不可**：

1. **雲端防火牆限來源 IP**（網路層，決定「誰連得到」）
   - Lightsail：實例 → Networking → IPv4 Firewall，為 TCP `8080` 把 Source 從
     `Anywhere (0.0.0.0/0)` 改成 `Restricted to IP`，填你的固定對外 IP。
   - 沒設這步 = port 對全世界開放，弱密碼裸奔。

2. **CORS 加公網來源**（應用層，決定「瀏覽器請求被不被接受」）
   編輯 VPS 上 `user_data/config.json` 的 `api_server.CORS_origins`，加入公網 IP 的 port：
   ```json
   "CORS_origins": [
       "http://<vps-ip>:8080"
   ],
   ```
   - 限 IP **不能取代** CORS：防火牆放你進門後，freqtrade 仍會檢查請求 Origin。沒加 CORS 的
     典型症狀是「頁面打得開但登入失敗 / 一片空白 / 資料載不出來」。
   - `127.0.0.1` / `localhost` 那兩條純公網存取用不到，但留著當後路（之後想走 SSH tunnel 免改）。

3. 改完 config 後重啟套用：`docker compose down && docker compose up -d`，
   再 `docker compose ps` 確認 PORTS 欄是 `0.0.0.0:8080->8080`（不是 `127.0.0.1:8080->8080`）。

瀏覽器開 `http://<vps-ip>:8080`。

> 公網部署務必先換掉 `config.json` 的弱密碼（`leon` / `aaaaa`）與 `jwt_secret_key`，
> IP 限制 + 強密碼雙保險。

### 方法 B：SSH tunnel（不開公網，最安全）

把 `docker-compose.yml` 的 `8080:8080` 改回 `127.0.0.1:8080:8080`，
`docker compose up -d` 後，從本機開隧道：

```bash
ssh -L 8080:localhost:8080 <user>@<vps-ip>
```

維持連線時瀏覽器開 `http://localhost:8080`。此法不需動防火牆 / CORS（既有的 localhost 白名單已涵蓋）。

---

## 常用維運指令

```bash
docker compose restart donchian    # 只重啟單一 bot
docker compose pull && docker compose up -d   # 更新 image 後重建
docker compose down                # 全部停止並移除容器（sqlite 錢包保留在 user_data）
```

改了策略 .py 或 config 後：`docker compose restart`（或單一 service）即可生效。

## 版本對齊（建議）

本機鎖定 freqtrade 2026.5.1。為求 VPS 行為一致，把 `docker-compose.yml` 的
`image: freqtradeorg/freqtrade:stable` 改成對應版本 tag（如 `:2026.5`），
可用 `docker run --rm freqtradeorg/freqtrade:stable freqtrade --version` 比對。
