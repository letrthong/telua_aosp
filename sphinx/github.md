 

## (Tùy chọn) GitHub Pages

`gh-pages` **không phải thư mục có sẵn trên GitHub** — nó là một **branch đặc biệt**
do chính bạn tạo ra. GitHub quy ước: nếu repo có branch tên `gh-pages`, nội dung
của branch đó sẽ được publish thành website tĩnh.

### GitHub Pages hoạt động ở đâu

```
Repo: github.com/<user>/<repo>
│
├── branch main        ← code nguồn (docs/*.md, build_apk.sh...)
├── branch gh-pages    ← HTML tĩnh (_build/html) ← GitHub lấy NỘI DUNG branch này làm website
│
└── Settings → Pages   ← nơi bạn BẬT tính năng và chọn "Source: gh-pages branch"
```

Sau khi bật, website live tại: `https://<user>.github.io/<repo>/`

### 3 lựa chọn Source trong Settings → Pages

| Source | Ý nghĩa |
|---|---|
| **Deploy from a branch** → `gh-pages` | GitHub lấy HTML tĩnh từ branch `gh-pages` (thủ công, phù hợp Sphinx) |
| **Deploy from a branch** → `main` + `/docs` folder | Chỉ hợp lệ khi HTML build nằm trong `docs/` của main (không dùng ở đây vì `docs/` chứa nguồn `.md`) |
| **GitHub Actions** | Workflow tự build Sphinx rồi deploy (tự động nhất) |

### Luồng publish

```
docs/*.md (branch main)
    │  make docs-build
    ▼
_build/html
    │  ghp-import
    ▼
branch gh-pages (chỉ chứa HTML)
    │  GitHub Pages
    ▼
https://user.github.io/telua_aosp
```

### Các bước thực hiện

```bash
# 1. Build HTML
cd ~/telua_aosp/docs && ./start_doc.sh build

# 2. Cài ghp-import (1 lần)
pip install ghp-import

# 3. Push _build/html lên branch gh-pages
cd ~/telua_aosp
ghp-import -n -p -f docs/_build/html
#        │  │  └ force push
#        │  └ push lên remote
#        └ không commit timestamp
```

Lần chạy đầu, `ghp-import` **tự tạo branch `gh-pages`** trên GitHub. Sau đó:

4. Vào **Settings → Pages → Source: Deploy from a branch → chọn `gh-pages` + `/ (root)` → Save**
   (chỉ cần làm **1 lần duy nhất**).
5. Từ lần sau, chỉ cần chạy lại `ghp-import -n -p -f docs/_build/html` — website tự cập nhật.

### Kiểm tra branch tồn tại

```bash
git branch -a                                    # local
git ls-remote --heads origin | grep gh-pages     # trên GitHub
```

## Khắc phục sự cố

| Vấn đề | Cách xử lý |
|---|---|
| `status` báo STOPPED dù server chạy | `rm -f /tmp/.autogen-sphinx-docs.pid` rồi `./start_doc.sh run` |
| Port 8080 bị chiếm | `pkill -f "http.server 8080"` rồi chạy lại |
| Build lỗi sau khi sửa `.md` | Chạy `./start_doc.sh build` để xem lỗi chi tiết (strict `-W` mode) |
| Venv hỏng / sai Python version | `rm -rf .docascode && ./start_doc.sh env` |
