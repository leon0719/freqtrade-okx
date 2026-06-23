# freqtrade-okx — 常用指令封裝
# 用法：make <target>，可覆寫變數，例如：
#   make download DAYS=60 TF=15m
#   make backtest TIMERANGE=20260518-
#   make new-strategy NAME=MyStrategy

# ---- 可覆寫變數 -------------------------------------------------------------
FT        := uv run freqtrade
CONFIG    := user_data/config.json
STRAT     := DonchianBreakout
TF        := 1h
PAIRS     := BTC/USDT ETH/USDT SOL/USDT
DAYS      := 30
TIMERANGE :=
LOSS      := SharpeHyperOptLoss
EPOCHS    := 100
SPACES    := buy sell roi stoploss

# TIMERANGE 有值時才帶 --timerange 參數
TR_ARG := $(if $(TIMERANGE),--timerange $(TIMERANGE),)

.DEFAULT_GOAL := help

# ---- 說明 -------------------------------------------------------------------
.PHONY: help
help: ## 顯示這份說明
	@echo "freqtrade-okx 常用指令："
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "可覆寫變數：STRAT=$(STRAT)  TF=$(TF)  DAYS=$(DAYS)  PAIRS='$(PAIRS)'"

# ---- 環境 / 設定 ------------------------------------------------------------
.PHONY: config
config: ## 驗證並顯示解析後的設定
	$(FT) show-config --config $(CONFIG)

.PHONY: strategies
strategies: ## 列出可用策略
	$(FT) list-strategies --config $(CONFIG)

# ---- 資料 -------------------------------------------------------------------
.PHONY: download
download: ## 下載歷史 K 線（可改 PAIRS / TF / DAYS）
	$(FT) download-data --config $(CONFIG) --pairs $(PAIRS) --timeframe $(TF) --days $(DAYS)

.PHONY: list-data
list-data: ## 列出已下載的資料
	$(FT) list-data --config $(CONFIG)

# ---- 回測 / 最佳化 ----------------------------------------------------------
.PHONY: backtest
backtest: ## 回測（可帶 TIMERANGE=20260518-）；--export signals 供 backtest-analysis 用
	$(FT) backtesting --config $(CONFIG) -s $(STRAT) --timeframe $(TF) $(TR_ARG) --export signals

.PHONY: backtest-show
backtest-show: ## 顯示最近一次回測結果
	$(FT) backtesting-show --config $(CONFIG)

.PHONY: lookahead
lookahead: ## 檢查策略是否有未來函數（look-ahead bias）
	$(FT) lookahead-analysis --config $(CONFIG) -s $(STRAT) $(TR_ARG)

.PHONY: hyperopt
hyperopt: ## 超參數最佳化（可改 LOSS / EPOCHS / SPACES）
	$(FT) hyperopt --config $(CONFIG) -s $(STRAT) --hyperopt-loss $(LOSS) \
	  --spaces $(SPACES) -e $(EPOCHS) $(TR_ARG)

.PHONY: hyperopt-show
hyperopt-show: ## 顯示最佳 hyperopt 結果
	$(FT) hyperopt-show --config $(CONFIG) --best

# ---- 分析（找出哪些訊號賺賠、優化進出場）------------------------------------
.PHONY: backtest-analysis
backtest-analysis: ## 分析最近一次回測的進出場原因（需先 make backtest）
	$(FT) backtesting-analysis --config $(CONFIG) --analysis-groups 0 1 2 3 4

.PHONY: recursive
recursive: ## 檢查指標遞迴穩定性（recursive bias）
	$(FT) recursive-analysis --config $(CONFIG) -s $(STRAT) $(TR_ARG)

# ---- 模擬盤 / UI ------------------------------------------------------------
.PHONY: trade
trade: ## 啟動模擬盤 dry-run（同時開 Web UI，http://127.0.0.1:8080）
	$(FT) trade --config $(CONFIG) -s $(STRAT)

.PHONY: webserver
webserver: ## 只開 Web 伺服器（回測分析用，不下單）
	$(FT) webserver --config $(CONFIG)

# ---- 雲端常駐部署（Docker Compose，見 docs/DEPLOY.md）------------------------
.PHONY: up
up: ## 背景常駐啟動 dry-run bot（VPS 用，--build 確保套用 Dockerfile 的 ccxt 修正）
	docker compose up -d --build

.PHONY: down
down: ## 停止並移除常駐容器（sqlite 錢包保留）
	docker compose down

.PHONY: logs
logs: ## 追常駐 bot 的即時 log（Ctrl-C 只離開 log，不停 bot）
	docker compose logs -f

.PHONY: ps
ps: ## 查看常駐 bot 狀態
	docker compose ps

# ---- 開發 -------------------------------------------------------------------
.PHONY: new-strategy
new-strategy: ## 建新策略範本，需帶 NAME=MyStrategy
	@test -n "$(NAME)" || { echo "用法：make new-strategy NAME=MyStrategy"; exit 1; }
	$(FT) new-strategy --config $(CONFIG) -s $(NAME)

.PHONY: clean
clean: ## 清除 Python 快取（__pycache__）
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.PHONY: clean-results
clean-results: ## 清除指令產出：回測 / hyperopt 結果、圖檔、log
	rm -rf user_data/backtest_results/* \
	       user_data/hyperopt_results/* \
	       user_data/plot/* \
	       user_data/logs/* 2>/dev/null || true
	@echo "已清除回測 / hyperopt 結果、圖檔與 log（原始資料與策略檔保留）"

.PHONY: clean-all
clean-all: clean clean-results ## 清除快取 + 所有指令產出物
