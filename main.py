from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal, ROUND_HALF_UP
import requests
from bs4 import BeautifulSoup
from pykrx import stock
from datetime import datetime, timedelta
import uvicorn
import traceback

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_naver_global_price(symbol: str):
    """해외 주식 전용: 네이버 증권 크롤링"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    
    # 네이버 해외 주식 시장 구분 접미사 순차 시도
    suffixes = ["", ".O", ".N", ".AM"] 
    
    for suffix in suffixes:
        target = symbol.upper() + suffix
        url = f"https://finance.naver.com/world/sise.naver?symbol={target}"
        
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code != 200:
                continue
                
            soup = BeautifulSoup(res.text, 'html.parser')
            price_tag = soup.select_one(".no_today .blind")
            
            if price_tag and price_tag.text.strip():
                price_str = price_tag.text.strip().replace(",", "")
                # 소수점 포함 숫자 여부 확인 후 Decimal 변환
                if price_str.replace(".", "").isdigit():
                    return Decimal(price_str)
        except:
            continue
    return None

@app.get("/search/{query}")
async def search_stock(query: str):
    """네이버 API 통합 검색 (국내 6자리, 해외 티커 찾기용)"""
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=1&frm=stock&r_format=json"
        res = requests.get(url, timeout=5)
        data = res.json()
        items = data.get('items', [[]])[0]
        # 검색 결과 가공
        results = []
        for item in items:
            results.append({
                "name": item[0],
                "symbol": item[1],
                "type": "KR" if item[4] == '1' else "US/Global"
            })
        return {"items": results}
    except Exception as e:
        return {"items": [], "error": str(e)}

@app.get("/price/{symbol}")
async def get_price(symbol: str):
    """가격 조회: 6자리 숫자는 KRX, 그 외는 해외 네이버 크롤링"""
    try:
        # --- [CASE 1] 국내 주식: 종목 코드가 6자리 숫자인 경우 ---
        if symbol.isdigit() and len(symbol) == 6:
            try:
                today = datetime.now().strftime("%Y%m%d")
                # pykrx 데이터 호출
                df = stock.get_market_ohlcv(today, today, symbol)
                
                # 오늘 데이터 없으면(휴일/장전) 최근 7일치 뒤지기
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
                else:
                    raise HTTPException(status_code=404, detail="KRX 종목 정보를 찾을 수 없습니다.")
            except Exception as e:
                print(f"KRX Error: {e}")
                raise HTTPException(status_code=500, detail=f"KRX API 오류: {str(e)}")

        # --- [CASE 2] 해외 주식: 6자리 숫자가 아닌 모든 경우 (티커 등) ---
        else:
            price_dec = get_naver_global_price(symbol)
            if price_dec is not None:
                # 소수점 4자리 반올림
                formatted_price = price_dec.quantize(Decimal('0.0000'), rounding=ROUND_HALF_UP)
                return {
                    "symbol": symbol.upper(),
                    "market": "US/Global",
                    "price": str(formatted_price),
                    "currency": "USD"
                }
            else:
                raise HTTPException(status_code=404, detail="해외 종목 정보를 찾을 수 없습니다.")

    except HTTPException as he:
        raise he
    except Exception as e:
        # 상세 에러 로그 출력 (Render Logs 확인용)
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
