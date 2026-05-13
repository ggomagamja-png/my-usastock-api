from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal, ROUND_HALF_UP
import requests
from bs4 import BeautifulSoup
from pykrx import stock
from datetime import datetime, timedelta
import uvicorn
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_google_finance_price(symbol: str):
    """구글 파이낸스를 통해 해외 주식 현재가 추출"""
    # 구글 파이낸스 검색 URL (예: AAPL 주식 검색)
    url = f"https://www.google.com/search?q=google+finance+{symbol}"
    
    # 봇 차단 방지를 위한 브라우저 헤더 설정
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 구글 파이낸스 위젯에서 가격 데이터가 들어있는 클래스 탐색
        # 구글은 클래스명이 자주 바뀌지만, 'data-precision' 속성이나 특정 패턴을 가짐
        # 현재 가장 안정적으로 가격을 추출하는 CSS 선택자:
        price_tag = soup.find("span", {"data-precision": True}) or soup.select_one(".fx96Cc .YMlS7e") or soup.select_one(".I67m4c")
        
        if not price_tag:
            # 대체 방법: 텍스트 내에서 $ 뒤에 오는 숫자 패턴 찾기
            text_content = soup.get_text()
            match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d+))', text_content)
            if match:
                price_str = match.group(1).replace(",", "")
                return Decimal(price_str)
            return None

        # 가격 문자열 정제
        price_str = price_tag.text.replace("$", "").replace(",", "").strip()
        return Decimal(price_str)
        
    except Exception as e:
        print(f"Google Finance Error: {e}")
        return None

@app.get("/search/{query}")
async def search_stock(query: str):
    """네이버 API를 활용한 종목 검색 (가장 안정적)"""
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
    """국내(6자리): pykrx / 해외: Google Finance"""
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
            price_dec = get_google_finance_price(symbol.upper())
            if price_dec:
                formatted_price = price_dec.quantize(Decimal('0.0000'), rounding=ROUND_HALF_UP)
                return {
                    "symbol": symbol.upper(),
                    "market": "US/Global",
                    "price": str(formatted_price),
                    "currency": "USD"
                }
            
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
