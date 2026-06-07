"""수정된 7개 포스트 내용 검증"""
import requests, re, time

time.sleep(3)

checks = [
    (24, ["64A", "분양가", "288세대"]),
    (25, ["39타입", "세대", "청약접수"]),
    (26, ["임의공급", "세대", "청약접수"]),
    (27, ["분당센트로", "세대", "청약접수"]),
    (28, ["롯데캐슬", "세대", "청약접수"]),
    (29, ["동탄", "세대", "청약접수"]),
    (30, ["금강펜테리움", "세대", "청약접수"]),
]

all_ok = True
for pid, keywords in checks:
    r = requests.get(
        f"https://llmenginehistory.tistory.com/{pid}",
        headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"},
        timeout=10,
    )
    m = re.search(
        r'class="tt_article_useless_p_margin[^"]*">(.*?)<div class="container_postbtn',
        r.text, re.DOTALL
    )
    if m:
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        hit = any(kw in text for kw in keywords)
        status = "✅" if hit else "❌"
        if not hit:
            all_ok = False
        print(f"  [{pid}] {status} {text[:120]}")
    else:
        print(f"  [{pid}] ❌ 본문 패턴 없음")
        all_ok = False

print()
print("최종:", "✅ 전체 수정 확인됨" if all_ok else "❌ 일부 미수정")
