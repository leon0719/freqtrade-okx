# 自建 image：繼承官方 freqtrade，僅把 ccxt 升到最新版。
#
# 緣由：官方 :stable image（Python 3.14）內含的 ccxt 在 OKX 偶發回傳
# id=None 的市場資料時，set_markets() 的 keysort 會崩
#   TypeError: '<' not supported between instances of 'NoneType' and 'str'
# 導致 load_markets() 在啟動 / 週期 reload_markets() 時整個 bot fatal exit。
# 新版 ccxt 已移除有問題的 keysort，升級即可根治。
#
# 用法：docker compose up -d --build
# 升級後想釘住版本可把下面的 -U 改成 ccxt==<版本>。

FROM freqtradeorg/freqtrade:stable

USER root
RUN pip install --no-cache-dir -U ccxt
USER ftuser
