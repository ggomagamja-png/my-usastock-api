from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal, ROUND_HALF_UP
import requests
from bs4 import BeautifulSoup
from pykrx import stock
from datetime import datetime
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_naver_global_price(symbol: str):
    """해외 주식만 네이버 증권에서 가격 추출"""
    # 1. 네이버 검색 API를 통해 해외 종목의 정확한 내부 심볼(예: AAPL.O)을 찾음
    search_url = f"https://ac.finance.naver.com/ac?q={symbol}&q_enc=utf-8&st=1&frm=stock&r_format=json"
    try:
        search_res = requests.get(search_url).json()
        items = search_res.get('items', [[]])[0]
        
        # 해외 종목(type '2') 중 첫 번째 결과 사용
        target_symbol = None
        for item in items:
            if item[4] == '2': 
                target_symbol = item[1]
                break
        
        if not target_symbol:
            target_symbol = symbol # 검색 결과 없으면 입력값 그대로 시도

        # 2. 네이버 해외 주식 페이지 크롤링
        url = f"https://finance.naver.com/world/sise.naver?symbol={target_symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 현재가 추출
        price_tag = soup.select_one(".no_today .blind")
        if price_tag:
            price_str = price_tag.text.replace(",", "")
            return Decimal(price_str)
    except Exception as e:
        print(f"Naver Scraping Error: {e}")
    return None

@app.get("/search/{query}")
async def search_stock(query: str):
    """네이버 API 통합 검색 (국내/해외 코드 찾기용)"""
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=1&frm=stock&r_format=json"
        data = requests.get(url).json()
        items = data.get('items', [[]])[0]
        results = []
        for item in items:
            results.append({
                "name": item[0],
                "symbol": item[1],
                "type": "KR" if item[4] == '1' else "US/Global"
            })
        return {"items": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/price/{symbol}")
async def get_price(symbol: str):
    try:
        # 1. 국내 주식 (6자리 숫자) -> pykrx 사용
        if symbol.isdigit() and len(symbol) == 6:
            today = datetime.now().strftime("%Y%m%d")
            df = stock.get_market_ohlcv(today, today, symbol)
            
            # 장 시작 전이거나 휴일이면 최근 영업일 데이터 호출
            if df.empty:
                # 최근 7일 내의 데이터를 가져옴
                from datetime import timedelta
                start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
                df = stock.get_market_ohlcv(start_date, today, symbol)
            
            if not df.empty:
                price_raw = df['종가'].iloc[-1]
                price_dec = Decimal(str(price_raw))
                return {
                    "symbol": symbol,
                    "market": "KRX",
                    "price": str(price_dec.quantize(Decimal('1'))),
                    "currency": "KRW"
                }

        # 2. 해외 주식 (그 외) -> 네이버 크롤링 사용
        else:
            price_dec = get_naver_global_price(symbol.upper())
            if price_dec:
                # 해외 주식은 소수점 4자리 고정
                precise_price = price_dec.quantize(Decimal('0.0000'), rounding=ROUND_HALF_UP)
                return {
                    "symbol": symbol.upper(),
                    "market": "US/Global",
                    "price": str(precise_price),
                    "currency": "USD"
                }

        raise HTTPException(status_code=404, detail="종목 정보를 찾을 수 없습니다.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
