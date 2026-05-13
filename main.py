import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
import os
import re

app = FastAPI()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

@app.get("/")
def home():
    return {"status": "ok"}

@app.get("/stock")
def get_stock_data(name: str = Query(None)):
    if not name:
        return {"name": None, "price": "0"}

    try:
        # 네이버 검색 결과 페이지 가져오기
        url = f"https://search.naver.com/search.naver?query={name}+주가"
        res = requests.get(url, headers=HEADERS, timeout=5)
        html = res.text
        soup = BeautifulSoup(html, 'html.parser')

        # 가격 정보 추출 (여러 영역 통합 검색)
        price = "0"
        price_candidates = soup.select(".price_info strong, .s0p_nm, .n_price strong, .api_biz_stock_price")
        
        if price_candidates:
            # 숫자만 추출
            price = re.sub(r'[^0-9]', '', price_candidates[0].text)
        else:
            # 태그 실패 시 정규식으로 '현재가' 키워드 주변 숫자 검색
            match = re.search(r'현재가.*?([0-9,]{3,10})', html)
            if match:
                price = match.group(1).replace(",", "")

        # 최종 결과 반환
        if price == "0":
            return {"name": name, "price": "데이터없음"}
            
        return {
            "name": name,
            "price": price
        }

    except Exception as e:
        return {"name": name, "price": "에러", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    # Render 등 클라우드 환경의 PORT 환경변수 대응
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
