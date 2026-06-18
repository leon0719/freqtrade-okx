# 部署到雲端常駐主機（VPS + Docker）

把三個 dry-run bot 搬到一台**不會睡眠**的主機常駐，解決「本機睡眠 / 關機 bot 就停」的問題。
用 Docker Compose + freqtrade 官方 image，不需在 VPS 上裝 Python / TA-Lib。

> 仍是 **dry-run（模擬盤）**，不碰真錢，也不需要 OKX API key。
> 之後若要實盤，再依 `CLAUDE.md` 的實盤檢查清單調整。

## 為什麼不用 Cloudflare Worker

Worker 是「定時觸發、跑幾秒就結束」的短命無狀態模型（像 `line-daily-report`），
而 freqtrade 需要**常駐 Python 行程 + 原生 TA-Lib + 與交易所長連線 + 持久狀態**，
兩者本質不相容。長時間掛 bot 該用常駐主機 / 容器。
（不過「每日把績效推到 LINE」這種定時通知很適合做成 Worker，之後可另外加。）

---

## 一、準備一台 VPS

任何便宜的 Linux VPS 即可（Hetzner / Vultr / DigitalOcean，~$5/月，1 vCPU / 1GB RAM 夠跑三個 dry-run bot）。
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
- `user_data/ema-trend.json`、`user_data/vol-breakout.json`
- `user_data/strategies/`（三個策略 .py）

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
docker compose up -d        # 背景常駐三個 bot
docker compose ps           # 看狀態
docker compose logs -f      # 看即時 log（Ctrl-C 只是離開 log，不會停 bot）
```

`restart: unless-stopped` 會在 VPS 重開機 / 容器崩潰時自動把 bot 拉回來。

## 五、連 Web UI（SSH tunnel，安全做法）

UI port 只綁在 VPS 的 `127.0.0.1`，不直接對公網開放。從你本機開隧道：

```bash
ssh -L 8080:localhost:8080 -L 8081:localhost:8081 -L 8082:localhost:8082 <user>@<vps-ip>
```

維持這條 SSH 連線時，本機瀏覽器開：

- http://localhost:8080 — DonchianBreakout
- http://localhost:8081 — EmaTrendFollow
- http://localhost:8082 — VolBreakout

帳密見 `config.json` 的 `api_server.username / password`。

> 想直接用 `http://<vps-ip>:8080` 連？要先在 `docker-compose.yml` 把 `127.0.0.1:8080:8080`
> 改成 `8080:8080`，**並且**先換掉 UI 弱密碼 + 設防火牆白名單，否則等於把帳號裸奔在公網。

---

## 常用維運指令

```bash
docker compose restart ema-trend   # 只重啟單一 bot
docker compose pull && docker compose up -d   # 更新 image 後重建
docker compose down                # 全部停止並移除容器（sqlite 錢包保留在 user_data）
```

改了策略 .py 或 config 後：`docker compose restart`（或單一 service）即可生效。

## 版本對齊（建議）

本機鎖定 freqtrade 2026.5.1。為求 VPS 行為一致，把 `docker-compose.yml` 的
`image: freqtradeorg/freqtrade:stable` 改成對應版本 tag（如 `:2026.5`），
可用 `docker run --rm freqtradeorg/freqtrade:stable freqtrade --version` 比對。
