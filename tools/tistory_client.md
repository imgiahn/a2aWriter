# 티스토리 연동 노하우 (tistory_client.md)

이 문서는 `tools/tistory_client.py` 구현 과정에서 축적한 티스토리 연동 노하우를 정리한다.
새 기능 개발 전 반드시 이 파일을 먼저 읽을 것.

---

## 1. 인증 / 세션

### Playwright persistent context
```python
ctx = pw.chromium.launch_persistent_context(
    user_data_dir="browser_data",
    headless=True,
    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
)
```
- `browser_data/` 폴더에 카카오 쿠키가 영구 저장됨
- 세션 살아있으면 재로그인 불필요
- EC2 서버에서 headless 실행 시 `--disable-dev-shm-usage --disable-gpu` 필수

### 카카오 자동 로그인 선택자
```
로그인 버튼:   a.link_kakao_id
이메일:        input[name='loginId']
비밀번호:      input[name='password']
제출:          button[type='submit']
```
- 세션 만료 확인: `/manage` 이동 후 URL에 `login`이 없으면 유효
- 로그인 후 `ctx.cookies()`로 쿠키 추출해 PUT API에 재사용

### 세션 만료 시
- 로컬: `python setup_browser.py` 실행 (카카오 앱 승인 필요할 수 있음)
- EC2 새 IP 첫 로그인 시 카카오 이메일 인증 요구할 수 있음

---

## 2. 신규 포스트 발행

### 에디터 진입
```python
page.goto(f"{blog_url}/manage/newpost/")
```

### 제목 입력
```python
page.locator("#post-title-inp, textarea[id*='title']").first.fill(title)
```

### 본문 입력 (tinyMCE)
```python
page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null")
page.evaluate("(html) => { const ed=tinyMCE.activeEditor; ed.focus(); ed.setContent(html); ed.save(); }", html)
```
⚠️ **중요**: `setContent()`은 **빈 에디터(신규 글)에서만** 정상 동작한다.
기존 포스트 편집 시에는 React 내부 상태를 갱신하지 못해 저장이 안 됨 → [섹션 3] 참고

### 발행 모달 처리
```python
page.locator("button:has-text('완료'), button:has-text('발행')").first.click()
modal = page.locator(".ReactModal__Content.editor_layer")
modal.wait_for(state="visible", timeout=8000)
page.locator("#open20").check()          # 공개 라디오
page.evaluate("document.getElementById('publish-btn').click()")
```

### 15개 포스트 제한 (무료 플랜)
- 15개 초과 시 발행이 임시저장으로 처리됨
- publisher가 "완료"를 출력해도 실제 발행이 안 된 경우 여기를 의심

---

## 3. 기존 포스트 수정

### ❌ tinyMCE setContent — 기존 포스트에서는 작동 안 함
```python
# 이 방법은 신규 글에서만 동작
ed.setContent(html)   # 기존 포스트: React 상태 갱신 안 됨 → 저장해도 구버전
ed.selection.select(ed.getBody(), true)
ed.selection.setContent(html)  # 이것도 마찬가지
iframe.contentDocument.body.innerHTML = html  # DOM은 바뀌지만 저장 안 됨
```

### ✅ PUT API 직접 호출 — 유일하게 확실한 방법
```python
PUT /manage/post/{id}.json
Content-Type: application/json;charset=UTF-8
Referer: {blog_url}/manage/newpost/{id}?type=post
Origin: {blog_url}
X-Requested-With: XMLHttpRequest
Cookie: (Playwright ctx.cookies()로 추출)
```

#### 필수 payload (필드 누락 시 비정상 동작)
```json
{
  "id": "24",
  "title": "제목",
  "content": "<html>",
  "slogan": "제목-slug",
  "visibility": 20,        // ← 반드시 20(공개). 누락 시 비공개로 전환됨!
  "category": 0,
  "tag": "",
  "acceptComment": 1,
  "published": 0,          // 0 = 기존 발행 시각 유지
  "password": "",
  "uselessMarginForEntry": 1,
  "daumLike": null,
  "cclCommercial": 0,
  "cclDerive": 0,
  "thumbnail": null,
  "type": "post",
  "attachments": [],
  "recaptchaValue": "",
  "draftSequence": null,
  "totalWritingTimeMs": 5000
}
```

#### GET /manage/post/{id}.json → 400 반환
payload를 직접 구성해야 한다. GET으로 기존 값을 가져올 수 없음.

---

## 4. 포스트 탐색 (manage/posts 페이지)

### HTML 구조
```html
<li>
  <div class="post_cont">
    <strong class="tit_post">
      <a class="link_cont" href="..." title="포스트 제목">포스트 제목</a>
    </strong>
  </div>
  <div class="post_btn">
    <a class="btn_post" href="/manage/post/24?returnURL=...">수정</a>  ← 편집 버튼
    <a class="btn_post" href="/manage/statistics/entry/24">통계</a>    ← 통계 버튼
  </div>
</li>
```

### 포스트 ID 추출 패턴
```javascript
// a.link_cont → closest('li') → a.btn_post → href에서 ID 추출
const container = lk.closest('li');
const btn = container.querySelector('a.btn_post');
const m = btn.getAttribute('href').match(/\/manage\/post\/(\d+)/);
const postId = m[1];
```
⚠️ `a.btn_post`를 인덱스로 매핑하면 안 됨. 통계 버튼도 같은 클래스라 인덱스 어긋남.

---

## 5. writer --dry-run 출력 경로

```python
# writer_agent.py --dry-run
# → articles/{blog}/preview/{task_id}.html  (draft/ 가 아님!)
```
수정 발행 시 `draft/`가 아닌 `preview/` 폴더 파일을 사용해야 한다.

---

## 6. Playwright route 인터셉터 한계

```python
page.route("**/24.json", handler)
# handler에서 route.continue_(post_data=...) 로 body 교체
```
- 인터셉트 자체는 성공해도 서버가 수정된 내용을 무시하는 경우가 있음
- 쿠키 기반 직접 PUT 호출이 더 안정적

---

## 7. Tistory API 엔드포인트 요약

| 기능 | 방법 |
|------|------|
| 신규 발행 | Playwright + tinyMCE + 발행 모달 |
| 기존 수정 | `PUT /manage/post/{id}.json` (쿠키 필요) |
| 목록 조회 | Playwright `/manage/posts` 파싱 |
| 삭제 | 미구현 (manage/posts에서 checkbox 선택 후 삭제 버튼) |
| 임시저장 | `PUT` payload에 `visibility: 0` |

---

## 8. 환경변수

```
KAKAO_EMAIL=...      # 카카오 로그인 이메일
KAKAO_PASSWORD=...   # 카카오 비밀번호
```
