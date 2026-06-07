"""fileUpload 플러그인 소스에서 업로드 API 엔드포인트 탐색"""
import requests, re

# fileUpload 플러그인 소스
r = requests.get("https://t1.kakaocdn.net/axz_keditor/dist/0.9.0/plugins/fileUpload/plugin.min.js", timeout=10)
src = r.text
print("플러그인 소스 크기:", len(src), "자")

# URL 패턴 탐색
urls = re.findall(r'["\']([^"\']*(?:upload|attach|file)[^"\']*)["\']', src)
print("\nURL/경로 패턴:")
for u in sorted(set(urls)):
    if len(u) > 3:
        print(" ", u)

# ajax/fetch 호출 탐색
ajax_calls = re.findall(r'(?:url|endpoint|api)["\']?\s*[:=]\s*["\']([^"\']+)["\']', src)
print("\nAJAX 호출 URL:")
for u in set(ajax_calls):
    print(" ", u)

# manage/ 경로 탐색
manage_paths = re.findall(r'["\'](?:/manage/[^"\']+)["\']', src)
print("\nmanage 경로:")
for p in set(manage_paths):
    print(" ", p)
