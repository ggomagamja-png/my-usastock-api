from fastapi import FastAPI, HTTPException
from decimal import Decimal, ROUND_HALF_UP
import yfinance as yf
from pykrx import stock
from datetime import datetime
import uvicorn

app = FastAPI()

def to_decimal(value):
    """모든 입력을 정밀 계산 가능한 Decimal로 변환"""
    return Decimal(str(value))

@app.get("/price/{symbol}")
def get_stock_data(symbol: str):
    try:
        # 1. 국내 주식 (6자리 숫자인 경우)
        if symbol.isdigit() and len(symbol) == 6:
            today = datetime.now().strftime("%Y%m%d")
            # KRX에서 당일 종가 가져오기
            df = stock.get_market_ohlcv(today, today, symbol)
            
            if df.empty:
                # 장 시작 전이거나 휴일일 경우 최근 영업일 데이터 호출
                df = stock.get_market_ohlcv("20240101", today, symbol)
            
            if not df.empty:
                price = to_decimal(df['종가'].iloc[-1])
                return {
                    "symbol": symbol,
                    "market": "KOSPI/KOSDAQ",
                    "price": str(price.quantize(Decimal('1'))), # 국내는 소수점 없음
                    "currency": "KRW"
                }

        # 2. 해외 주식 (티커 입력 시)
        else:
            ticker = yf.Ticker(symbol)
            # info에서 현재가 추출
            raw_price = ticker.info.get('currentPrice') or ticker.info.get('regularMarketPrice')
            
            if raw_price:
                price_dec = to_decimal(raw_price)
                # 소수점 4자리까지 고정 (계산용 데이터)
                precise_price = price_dec.quantize(Decimal('0.0000'), rounding=ROUND_HALF_UP)
                
                return {
                    "symbol": symbol.upper(),
                    "market": "US/Global",
                    "price": str(precise_price), # JSON 전달을 위해 문자열 변환
                    "currency": "USD"
                }

        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
