"""포스트 24번 og:image 및 본문 확인"""
import requests, re

r = requests.get("https://llmenginehistory.tistory.com/24",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=10)

# og:image 태그
m = re.search(r'og:image.*?content=["\']([^"\']+)["\']', r.text)
print("og:image:", m.group(1)[:100] if m else "없음")

# 본문
m2 = re.search(r'class="tt_article_useless_p_margin[^"]*">(.*?)<div class="container_postbtn',
               r.text, re.DOTALL)
if m2:
    text = re.sub(r"<[^>]+>", " ", m2.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    print("본문 앞150:", text[:150])
