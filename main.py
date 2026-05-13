from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal, ROUND_HALF_UP
import yfinance as yf
from pykrx import stock
from datetime import datetime, timedelta
import uvicorn
import requests


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# yfinance 차단 우회를 위한 세션 설정
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

@app.get("/search/{query}")
async def search_stock(query: str):
    """검색은 네이버 API 활용 (가장 빠름)"""
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=1&frm=stock&r_format=json"
        res = requests.get(url, timeout=5)
        data = res.json()
        items = data.get('items', [[]])[0]
        results = [{"name": item[0], "symbol": item[1], "type": "KR" if item[4] == '1' else "US/Global"} for item in items]
        return {"items": results}
    except:
        return {"items": []}

@app.get("/price/{symbol}")
async def get_price(symbol: str):
    """국내(6자리): pykrx / 해외: yfinance(세션 우회)"""
    try:
        # 1. 국내 주식 (6자리 숫자)
        if symbol.isdigit() and len(symbol) == 6:
            today = datetime.now().strftime("%Y%m%d")
            df = stock.get_market_ohlcv(today, today, symbol)
            
            if df is None or df.empty:
                start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
                df = stock.get_market_ohlcv(start_date, today, symbol)
            
            if df is not None and not df.empty:
                price_raw = df['종가'].iloc[-1]
                return {
                    "symbol": symbol,
                    "market": "KRX",
                    "price": str(int(price_raw)),
                    "currency": "KRW"
                }

        # 2. 해외 주식 (그 외)
        else:
            # 세션을 사용하여 차단 우회
            ticker = yf.Ticker(symbol.upper(), session=session)
            
            # fast_info는 차단에 더 강하고 빠릅니다
            price_raw = None
            try:
                price_raw = ticker.fast_info['last_price']
            except:
                # fast_info 실패 시 기본 info 시도
                info = ticker.info
                price_raw = info.get('currentPrice') or info.get('regularMarketPrice')

            if price_raw:
                price_dec = Decimal(str(price_raw))
                formatted_price = price_dec.quantize(Decimal('0.0000'), rounding=ROUND_HALF_UP)
                return {
                    "symbol": symbol.upper(),
                    "market": "US/Global",
                    "price": str(formatted_price),
                    "currency": "USD"
                }
            
        raise HTTPException(status_code=404, detail="종목 정보를 가져올 수 없습니다.")

    except Exception as e:
        print(f"Error for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
