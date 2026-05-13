from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal, ROUND_HALF_UP
import yfinance as yf
from pykrx import stock
import uvicorn
import asyncio

app = FastAPI()

# CORS 설정: 브라우저에서 API를 호출할 때 발생하는 보안 차단 방지
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 글로벌 캐시 변수
KRX_CACHE = []

@app.on_event("startup")
async def load_krx_data():
    """서버 시작 시 국내 종목 리스트를 메모리에 로드 (매번 리스트 훑기 방지)"""
    global KRX_CACHE
    print("🚀 국내 종목 리스트 로드 중...")
    try:
        # 코스피, 코스닥 종목 리스트를 한 번에 가져와 메모리에 저장
        combined_list = []
        for market in ["KOSPI", "KOSDAQ"]:
            tickers = stock.get_market_ticker_list(market=market)
            for t in tickers:
                name = stock.get_market_ticker_name(t)
                combined_list.append({
                    "name": name,
                    "symbol": t,
                    "market": market,
                    "type": "KR"
                })
        KRX_CACHE = combined_list
        print(f"✅ 로드 완료: {len(KRX_CACHE)} 종목 저장됨.")
    except Exception as e:
        print(f"❌ 로드 실패: {e}")

@app.get("/search/{query}")
async def search_stock(query: str):
    """국내/해외 종목 검색 (메모리 캐시 + yfinance)"""
    # 1. 국내 주식 검색 (메모리에서 즉각 필터링)
    kr_results = [item for item in KRX_CACHE if query.lower() in item['name'].lower()]
    
    # 2. 해외 주식 검색 (yfinance Search API 활용)
    us_results = []
    try:
        # yfinance 검색은 별도 스레드에서 실행되도록 loop 활용 (FastAPI 권장)
        loop = asyncio.get_event_loop()
        yf_search = await loop.run_in_executor(None, lambda: yf.Search(query, max_results=5))
        
        for quote in yf_search.quotes:
            us_results.append({
                "name": quote.get("longname") or quote.get("shortname"),
                "symbol": quote.get("symbol"),
                "market": quote.get("exchange"),
                "type": "US/Global"
            })
    except Exception:
        pass

    return {
        "query": query,
        "total": len(kr_results) + len(us_results),
        "items": kr_results + us_results
    }

@app.get("/price/{symbol}")
async def get_stock_price(symbol: str):
    """종목 코드 또는 티커로 현재가 조회 (소수점 4자리 정밀 계산)"""
    try:
        # 국내 주식 (6자리 숫자)
        if symbol.isdigit() and len(symbol) == 6:
            # pykrx는 동기 방식이므로 마지막 종가를 가져옴
            price_raw = stock.get_market_ohlcv_by_date(None, None, symbol)['종가'].iloc[-1]
            price_dec = Decimal(str(price_raw))
            return {
                "symbol": symbol,
                "price": str(price_dec.quantize(Decimal('1'))), # 원화는 정수
                "currency": "KRW"
            }

        # 해외 주식 (티커)
        else:
            ticker = yf.Ticker(symbol)
            # info 호출 시 발생할 수 있는 딜레이를 위해 currentPrice 우선 확인
            info = ticker.info
            raw_price = info.get('currentPrice') or info.get('regularMarketPrice')
            
            if raw_price:
                price_dec = Decimal(str(raw_price)).quantize(Decimal('0.0000'), rounding=ROUND_HALF_UP)
                return {
                    "symbol": symbol.upper(),
                    "price": str(price_dec),
                    "currency": "USD"
                }
            
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
