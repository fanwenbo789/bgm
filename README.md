# bgm

BREEZE BLOG 的 Bangumi 追番数据仓库，由 GitHub Actions 定时同步，GitHub Pages 提供静态访问。

## 地址

- 数据：<https://fanwenbo789.github.io/bgm/data.json>
- 封面：`https://fanwenbo789.github.io/bgm/covers/<subject_id>.webp`
- 仓库：`fanwenbo789/bgm`（public）

追番页在 `https://www.breeze.moe/anime/` 运行时读取 `data.json`。

## 文件

- `sync.py`：拉取 Bangumi 动画收藏，过滤番外，下载并裁成 480×480 WebP 封面，写入 `data.json`
- `data.json`：页面数据，包含条目、进度、封面路径、进度条颜色
- `covers/`：480×480 WebP 封面
- `.github/workflows/sync.yml`：每天北京时间 12:00 同步，也可手动触发

## 本地运行

```bash
cd bgm
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export BGM_TOKEN='...'
python3 sync.py
```

也可以把 token 写到 `.bgm_token`（`chmod 600`，已 gitignore），脚本会自动读取。

## GitHub Actions

在仓库 Settings → Secrets and variables → Actions 添加：

- `BGM_TOKEN`：Bangumi Access Token，需要 `write:collection` 权限

工作流使用 `GITHUB_TOKEN` 提交数据，仓库 Settings → Actions → General → Workflow permissions 选择 **Read and write permissions**。

## GitHub Pages

Settings → Pages：

- Source: Deploy from a branch
- Branch: `main` / `(root)`

`.nojekyll` 已存在，避免 Jekyll 处理。

## 注意

- 仓库必须是 public（GitHub Free 的 Pages 只支持 public 仓库）。
- `data.json` 和封面是公开的，token 只存在 Actions secret 和本地 `.bgm_token`。
- GitHub Pages 的 JSON 响应带 `access-control-allow-origin: *`，追番页可以跨域 fetch。
- Pages 缓存约 10 分钟；追番页请求时会加时间戳绕过缓存。
- `github.io` 在境内可能不稳定；必要时用自定义域名或 jsDelivr 作为备用。
