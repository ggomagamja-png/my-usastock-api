from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

STOCK_CODES = {
    "현대차": "005380",
    "삼성전자": "005930",
    "카카오": "035720",
    "네이버": "035420"
}

@app.get("/api/stock/{stock_name}")
def get_stock_info(stock_name: str):
    if stock_name not in STOCK_CODES:
        return {"error": "종목을 찾을 수 없습니다."}
    
    code = STOCK_CODES[stock_name]
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        price_tag = soup.select_one('.no_today .blind')
        
        if price_tag:
            return {"name": stock_name, "code": code, "price": price_tag.text}
        else:
            return {"error": "가격을 불러올 수 없습니다."}
    except Exception as e:
        return {"error": "크롤링 실패"}
