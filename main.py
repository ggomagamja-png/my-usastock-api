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
    """해외 주식: 검색 API로 정확한 심볼을 찾은 후 크롤링"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    
    try:
        # 1. 네이버 검색 API를 통해 정확한 심볼(예: AAPL -> AAPL.O) 검색
        # 이 단계가 있어야 네이버 상세 페이지 URL을 정확히 맞출 수 있습니다.
        search_url = f"https://ac.finance.naver.com/ac?q={symbol}&q_enc=utf-8&st=1&frm=stock&r_format=json"
        search_res = requests.get(search_url, timeout=5).json()
        items = search_res.get('items', [[]])[0]
        
        target_symbol = symbol.upper() # 기본값
        for item in items:
            if item[4] == '2': # 해외 주식 타입인 경우
                target_symbol = item[1] # 네이버 전용 심볼(AAPL.O 등) 추출
                break

        # 2. 추출된 심볼로 상세 페이지 크롤링
        url = f"https://finance.naver.com/world/sise.naver?symbol={target_symbol}"
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        price_tag = soup.select_one(".no_today .blind")
        if price_tag:
            price_str = price_tag.text.strip().replace(",", "")
            if price_str.replace(".", "").isdigit():
                return Decimal(price_str), target_symbol
                
    except Exception as e:
        print(f"Scraping Error: {e}")
    return None, None

@app.get("/search/{query}")
async def search_stock(query: str):
    """종목 검색 기능"""
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=1&frm=stock&r_format=json"
        res = requests.get(url, timeout=5)
        data = res.json()
        items = data.get('items', [[]])[0]
        results = [{"name": item[0], "symbol": item[1], "type": "KR" if item[4] == '1' else "US/Global"} for item in items]
        return {"items": results}
    except Exception as e:
        return {"items": [], "error": str(e)}

@app.get("/price/{symbol}")
async def get_price(symbol: str):
    """가격 조회 (6자리 숫자: KRX, 그 외: 네이버 해외 크롤링)"""
    try:
        # [국내 주식] 6자리 숫자
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

        # [해외 주식] 그 외 모든 케이스
        else:
            price_dec, real_symbol = get_naver_global_price(symbol)
            if price_dec:
                formatted_price = price_dec.quantize(Decimal('0.0000'), rounding=ROUND_HALF_UP)
                return {
                    "symbol": real_symbol, # 네이버 실제 심볼 반환 (예: AAPL.O)
                    "market": "US/Global",
                    "price": str(formatted_price),
                    "currency": "USD"
                }
            
        raise HTTPException(status_code=404, detail="종목 정보를 찾을 수 없습니다.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
