import os
import logging
import aiohttp
import asyncio
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InputFile
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", CHANNEL_ID))

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

API_URL = "https://api.coingecko.com/api/v3"
TON_ID = "the-open-network"

logging.basicConfig(level=logging.INFO)

async def fetch_price_data():
    async with aiohttp.ClientSession() as session:
        try:
            # Current price
            async with session.get(f"{API_URL}/simple/price?ids={TON_ID}&vs_currencies=usd,idr") as resp:
                prices = await resp.json()
                usd = prices[TON_ID]["usd"]
                idr = prices[TON_ID]["idr"]

            # Market cap
            async with session.get(f"{API_URL}/coins/{TON_ID}") as resp:
                data = await resp.json()
                market_cap = data["market_data"]["market_cap"]["usd"]

            # 7d history
            async with session.get(f"{API_URL}/coins/{TON_ID}/market_chart?vs_currency=usd&days=7") as resp:
                chart_data = await resp.json()
                prices = chart_data["prices"]

            return usd, idr, market_cap, prices

        except Exception as e:
            await send_error(f"Error fetch data: {e}")
            return None

def generate_chart(prices):
    dates = [datetime.fromtimestamp(p[0]/1000).strftime('%b %d') for p in prices]
    values = [p[1] for p in prices]

    plt.figure(figsize=(8, 4))
    plt.plot(dates, values, marker='o')
    plt.xticks(rotation=45)
    plt.title("TON 7-Day Price (USD)")
    plt.tight_layout()
    plt.grid()
    filename = "ton_chart.png"
    plt.savefig(filename)
    plt.close()
    return filename

async def send_update():
    result = await fetch_price_data()
    if result is None:
        return
    usd, idr, market_cap, chart_data = result

    text = (
        f"💸 <b>Harga Toncoin</b>\n"
        f"<b>USD:</b> ${usd:,.2f}\n"
        f"<b>IDR:</b> Rp{idr:,.0f}\n\n"
        f"🪙 <b>Market Cap:</b> ${market_cap:,.0f}\n\n"
        f"♎️ <a href='https://www.coingecko.com/en/coins/the-open-network'>CoinGecko</a> | "
        f"<a href='https://coinmarketcap.com/currencies/toncoin/'>CoinMarketCap</a>"
    )

    chart_path = generate_chart(chart_data)

    try:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=InputFile(chart_path), caption=text)
    except TelegramAPIError as e:
        await send_error(f"Gagal kirim ke channel: {e}")

async def send_error(message):
    try:
        await bot.send_message(LOG_CHANNEL_ID, f"<b>[ERROR]</b> {message}")
    except:
        logging.error("Gagal kirim log ke Telegram.")

async def scheduler():
    while True:
        await send_update()
        await asyncio.sleep(600)  # 10 menit

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
