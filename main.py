from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal, ROUND_HALF_UP
import requests
from bs4 import BeautifulSoup
from pykrx import stock
from datetime import datetime, timedelta
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_naver_global_price(symbol: str):
    """해외 주식 가격 추출 (DNS 에러 방지를 위한 직접 접근 방식)"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    
    # 네이버 해외 주식은 티커 뒤에 시장 구분값(.O, .N, .AM)이 붙어야 합니다.
    # 사용자가 'AAPL'만 입력했을 경우를 대비해 주요 시장 접미사를 순회하며 시도합니다.
    suffixes = ["", ".O", ".N", ".AM"] 
    
    for suffix in suffixes:
        target = symbol + suffix
        url = f"https://finance.naver.com/world/sise.naver?symbol={target}"
        
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code != 200:
                continue
                
            soup = BeautifulSoup(res.text, 'html.parser')
            # 현재가 태그 추출
            price_tag = soup.select_one(".no_today .blind")
            
            if price_tag and price_tag.text.strip():
                price_str = price_tag.text.replace(",", "")
                return Decimal(price_str)
        except Exception as e:
            print(f"Scraping attempt failed for {target}: {e}")
            continue
            
    return None

@app.get("/search/{query}")
async def search_stock(query: str):
    """종목 검색 (DNS 에러 발생 시 빈 리스트 반환하여 전체 다운 방지)"""
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=1&frm=stock&r_format=json"
        res = requests.get(url, timeout=3)
        data = res.json()
        items = data.get('items', [[]])[0]
        results = [{"name": item[0], "symbol": item[1], "type": "KR" if item[4] == '1' else "US/Global"} for item in items]
        return {"items": results}
    except Exception as e:
        print(f"Search DNS/Connection Error: {e}")
        # 검색 API가 죽어도 전체 서비스는 동작하도록 빈 결과 반환
        return {"items": [], "error": "Search service temporarily unavailable"}

@app.get("/price/{symbol}")
async def get_price(symbol: str):
    try:
        # 1. 국내 주식 (6자리 숫자)
        if symbol.isdigit() and len(symbol) == 6:
            today = datetime.now().strftime("%Y%m%d")
            df = stock.get_market_ohlcv(today, today, symbol)
            
            if df.empty:
                start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
                df = stock.get_market_ohlcv(start_date, today, symbol)
            
            if not df.empty:
                price_raw = df['종가'].iloc[-1]
                return {
                    "symbol": symbol,
                    "market": "KRX",
                    "price": str(Decimal(str(price_raw)).quantize(Decimal('1'))),
                    "currency": "KRW"
                }

        # 2. 해외 주식 (그 외)
        else:
            price_dec = get_naver_global_price(symbol.upper())
            if price_dec:
                return {
                    "symbol": symbol.upper(),
                    "market": "US/Global",
                    "price": str(price_dec.quantize(Decimal('0.0000'), ROUND_HALF_UP)),
                    "currency": "USD"
                }

        raise HTTPException(status_code=404, detail="Symbol not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
