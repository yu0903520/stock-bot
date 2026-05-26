import discord
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time

# ======================
# Discord 設定
# ======================
TOKEN ="MTUwODcyMTEyODI4ODU1NTA0OQ.G4nZc4.ZiBIrZxdSd4ha9Sqn5mZeYQ4h6fuLCKH5O8Kak"
CHANNEL_ID = 1508722619560497165

client = discord.Client(intents=discord.Intents.default())

# ======================
# 股票池
# ======================
def get_twse():
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    r = requests.get(url, timeout=10).json()
    return [x["Code"] + ".TW" for x in r if x["Code"].isdigit()]

def get_tpex():
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
    r = requests.get(url, timeout=10).json()
    return [x["code"] + ".TWO" for x in r if x.get("code")]

# ======================
# RSI
# ======================
def RSI(close):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ======================
# 單檔分析（穩定版）
# ======================
def analyze(stock):
    try:
        df = yf.download(
            stock,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False
        )

        if df is None or df.empty or len(df) < 60:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        if volume.sum() == 0:
            return None

        # ======================
        # RSI
        # ======================
        rsi = RSI(close)

        # ======================
        # DMI
        # ======================
        up = high.diff()
        down = -low.diff()

        plus_dm = np.where((up > down) & (up > 0), up, 0)
        minus_dm = np.where((down > up) & (down > 0), down, 0)

        plus_dm = pd.Series(plus_dm, index=df.index)
        minus_dm = pd.Series(minus_dm, index=df.index)

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(14).mean()

        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)

        # ======================
        # 均線 / 成交量
        # ======================
        ma20 = close.rolling(20).mean()
        vol_ma20 = volume.rolling(20).mean()

        df2 = pd.DataFrame({
            "close": close,
            "rsi": rsi,
            "pdi": plus_di,
            "mdi": minus_di,
            "ma20": ma20,
            "volume": volume,
            "vol_ma": vol_ma20
        }).dropna()

        if len(df2) < 2:
            return None

        last = df2.iloc[-1]
        prev = df2.iloc[-2]

        # ======================
        # BUY條件（穩定版）
        # ======================
        buy = (
            (last["pdi"] > last["mdi"]) and
            (prev["pdi"] <= prev["mdi"]) and
            (last["close"] > last["ma20"]) and
            (last["rsi"] > 45) and
            (last["rsi"] < 70) and
            (last["volume"] > last["vol_ma"])
        )

        if buy:
            return (stock, last["volume"])

        return None

    except:
        return None

# ======================
# 掃描（穩定版）
# ======================
def scan_all():
    stocks = get_twse() + get_tpex()

    print("股票數:", len(stocks))

    results = []

    for i, s in enumerate(stocks):

        if i % 200 == 0:
            print(f"進度 {i}/{len(stocks)}")

        r = analyze(s)
        if r:
            results.append(r)

        time.sleep(0.02)  # 防止 Yahoo 卡你

    # 成交量排序
    results.sort(key=lambda x: x[1], reverse=True)

    return results

# ======================
# Discord 發送
# ======================
async def send_result():
    await client.wait_until_ready()

    channel = await client.fetch_channel(CHANNEL_ID)

    print("開始掃描...")
    results = await asyncio.to_thread(scan_all)
    print("掃描完成")

    msg = "🔥 今日 BUY 訊號 TOP10\n\n"

    if not results:
        msg += "無符合條件股票"
    else:
        for i, r in enumerate(results[:10]):
            msg += f"{i+1}. {r[0]} | Volume: {int(r[1])}\n"

    await channel.send(msg)

# ======================
# 啟動
# ======================
@client.event
async def on_ready():
    print("Bot已上線")
    client.loop.create_task(send_result())

client.run(TOKEN)