"""포스트 24번 실제 내용 확인"""
import requests, re

r = requests.get("https://llmenginehistory.tistory.com/24",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=10)

# tt_article 본문 추출
for pattern in [
    r'class="tt_article_useless_p_margin[^"]*">(.*?)<div class="container_postbtn',
    r'id="content"(.*?)</article>',
    r'<article[^>]*>(.*?)</article>',
]:
    m = re.search(pattern, r.text, re.DOTALL)
    if m:
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        print(f"패턴 매칭됨: 앞400자")
        print(text[:400])
        break
else:
    # table 태그 탐색
    tables = re.findall(r"<table[^>]*>.*?</table>", r.text, re.DOTALL)
    print(f"table {len(tables)}개")
    for i, t in enumerate(tables[:3]):
        txt = re.sub(r"<[^>]+>", " ", t)
        txt = re.sub(r"\s+", " ", txt).strip()
        print(f"  table[{i}]: {txt[:150]}")
