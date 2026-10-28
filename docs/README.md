# telua_aosp/docs — Sphinx Documentation

Tài liệu Sphinx (Markdown via MyST) cho **build_apk.sh — AOSP System APK Build & Deployment Toolkit**.

## Cấu trúc

```
docs/
├── index.md            # Trang chủ docs (nguồn — PUSH lên GitHub)
├── autogen_sphinx.py   # Bootstrapper scaffold (PUSH)
├── start_doc.sh        # Helper script chạy docs (PUSH)
├── README.md           # File này (PUSH)
├── conf.py             # GENERATED — KHÔNG push
├── Makefile            # GENERATED — KHÔNG push
├── requirements.txt    # GENERATED — KHÔNG push
├── .gitignore          # GENERATED — KHÔNG push
├── _build/             # Build output — KHÔNG push
├── _static/            # GENERATED — KHÔNG push
└── .docascode/         # Python venv — KHÔNG push
```

> `.gitignore` trong thư mục này đã tự động loại bỏ các file GENERATED.
> Chỉ cần `git add docs/` — Git tự bỏ qua phần generated.

## Sử dụng hàng ngày

```bash
cd ~/telua_aosp/docs

./start_doc.sh run      # build + serve tại http://localhost:8080 + mở browser
./start_doc.sh reload   # rebuild khi sửa .md (server giữ nguyên)
./start_doc.sh stop     # dừng server
./start_doc.sh clean    # xóa _build/
./start_doc.sh status   # xem trạng thái server
./start_doc.sh build    # chỉ build HTML (không chạy server)
./start_doc.sh env      # tạo venv + cài Sphinx dependencies (lần đầu)
```

Server chạy tại: **http://localhost:8080**

## Thêm trang docs mới

1. Tạo file `.md` mới trong `docs/` (ví dụ `cli.md`, `config.md`).
2. Thêm vào toctree trong `index.md`:

   ```markdown
   ```{toctree}
   :maxdepth: 2
   :caption: Documentation

   cli
   config
   ```
   ```

   (Tên file không cần đuôi `.md`.)
3. `./start_doc.sh reload` → refresh browser.

## Push lên GitHub

### Những gì được push (nguồn docs)

```bash
cd ~/telua_aosp
git add docs/
git status   # chỉ thấy: index.md, autogen_sphinx.py, start_doc.sh, README.md
git commit -m "docs: add Sphinx documentation for telua_aosp"
git push
```

### Những gì KHÔNG được push (đã bị .gitignore chặn)

| File/Dir | Lý do |
|---|---|
| `_build/` | Build artifact — regenerate từ `.md` bất cứ lúc nào |
| `.docascode/` | Python venv — máy-specific, nặng |
| `conf.py`, `Makefile`, `requirements.txt`, `.gitignore`, `_static/` | Generated bởi `autogen_sphinx.py --init` — ai cũng tự generate được |

> **Lưu ý:** `conf.py` chứa project name/tùy chọn cá nhân hóa. Nếu muốn
> chuẩn hóa config cho cả team (khuyến nghị khi có CI), xóa 3 dòng
> `conf.py`, `Makefile`, `requirements.txt` khỏi `docs/.gitignore` rồi
> commit chúng — khi đó `make docs-build` chạy nhất quán trên mọi máy.

### Xây lại docs sau khi clone (máy mới)

```bash
cd ~/telua_aosp/docs
python3 autogen_sphinx.py --init .   # scaffold conf.py, Makefile, requirements.txt
make env                             # tạo venv + cài deps
make docs-build                      # build HTML → _build/html/index.html
```

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
