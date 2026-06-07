"""포스트 24번 내용 확인 + PUT 응답 검증"""
import requests, re, time

# 캐시 무효화 헤더로 최신 버전 요청
r = requests.get("https://llmenginehistory.tistory.com/24",
                 headers={"User-Agent": "Mozilla/5.0",
                          "Cache-Control": "no-cache, no-store",
                          "Pragma": "no-cache"},
                 timeout=10)

m = re.search(r'class="tt_article_useless_p_margin[^"]*">(.*?)<div class="container_postbtn',
              r.text, re.DOTALL)
if m:
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    print("포스트 내용 앞500자:")
    print(text[:500])
    print()
    if "64A" in text or "분양가" in text or "288세대" in text:
        print("✅ 새 내용 확인됨 (분양가/타입 정보 있음)")
    elif "네이버 지도" in text and "분양정보" in text:
        print("❌ 여전히 구버전 (분양정보 빈 섹션)")
    else:
        print("? 내용 구분 불명확")
else:
    print("본문 패턴 매칭 실패")
