"""포스트 24번 상단 확인"""
import requests, re

r = requests.get("https://llmenginehistory.tistory.com/24",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
m = re.search(r'class="tt_article_useless_p_margin[^"]*">(.*?)<div class="container_postbtn',
              r.text, re.DOTALL)
if m:
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    print(text[:400])
