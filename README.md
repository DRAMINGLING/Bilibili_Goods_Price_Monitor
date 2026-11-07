# Bilibili 商品价格监控

本仓库通过 GitHub Actions 手动查询 Bilibili 会员购转售商品，记录价格历史，并按配置发送邮件提醒。价格面板由个人站点仓库提供；面板上的星标通过本仓库的 Cloudflare Worker 保存。价格监控没有定时计划，需要从 Actions 页面手动运行。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `config/products.yaml` | 邮件参数、商品链接、启用状态和价格条件 |
| `src/bilibili.py` | 读取商品详情接口并解析价格 |
| `src/main.py` | 查询商品、写入历史并按星标或条件发送提醒 |
| `src/conditions.py` | 判断价格条件 |
| `src/notifier.py` | 通过 SMTP SSL 发送提醒邮件 |
| `src/storage.py` | 读写、清理、合并和统计价格历史 |
| `src/git_sync.py` | 提交并推送价格历史 |
| `data/price_history.json` | 商品价格观测记录 |
| `data/starred_products.json` | 从价格面板选择的星标商品 ID |
| `worker/` | 保存星标状态的 Cloudflare Worker |
| `.github/workflows/price-monitor.yml` | 手动运行监控并提交历史 |
| `.github/workflows/sync-price-dashboard.yml` | 将历史数据同步到 GitHub Pages 仓库 |
| `tests/` | 查询、条件、通知、存储和工作流测试 |

## 当前商品配置

目前配置的启用商品都使用 `condition.type: "lte"`：当前价格小于或等于目标值时发送阈值提醒。

| 状态 | 商品 | `cluster_id` | 条件 |
| --- | --- | --- | --- |
| 启用 | FuRyu 泡面压 澄闪 现货 | `10000008690` | ≤ ¥50 |
| 启用 | BANPRESTO Re:0 雷姆 Sweet Angel ver. 预售 | `10000024408` | ≤ ¥70 |
| 启用 | FuRyu Trio-Try-iT 泉此方 现货 | `10000000653` | ≤ ¥100 |
| 启用 | Sega PM 波奇 现货 | `10000009511` | ≤ ¥80 |
| 启用 | Sega FIGURIZMa 义勇 预售 | `10000013380` | ≤ ¥65 |
| 启用 | TAITO AMP+ 伊蕾娜 现货 | `10000011221` | ≤ ¥60 |
| 停用 | FuRyu Trio-Try-iT 小镜 现货 | `10000000146` | ≤ ¥50 |
| 停用 | FuRyu Trio-Try-iT 小司 现货 | `10000001234` | ≤ ¥60 |
| 停用 | Sega FIGURIZMa 芙莉莲 现货 | `10000000164` | ≤ ¥45 |
| 停用 | VISION CHILLfigg 唯 预售 | `10000000940` | ≤ ¥60 |
| 停用 | VISION CHILLfigg 阿梓喵 预售 | `10000001118` | ≤ ¥65 |

`enabled: false` 的商品会被跳过；如果省略 `enabled`，程序默认启用。请求实际从 `url` 中读取 `clusterId`，修改商品时请同步更新 `url` 和 `cluster_id`。

YAML 中还配置了 `price_type` 和 `cooldown_hours`，但当前 `src/main.py` 没有读取这两个字段。查询仍使用接口返回的 `firstPrice`，而 `cooldown_hours` 不会阻止重复通知：每次手动运行时，只要未星标商品仍满足价格条件，就会再次尝试发送邮件。

## 查询、提醒与历史

`BilibiliFetcher` 请求市集公开 JSON 详情接口 `mall-search-items/items_detail/cluster_info`，并从 `data.clusterPriceFloorVO.priceTag.firstPrice` 解析价格。程序不解析动态 HTML，也不使用 Cookie 或登录凭证。接口错误或返回内容无法可靠解析时，该商品不会产生新的价格记录。

未星标商品按 `condition` 判断是否提醒。星标商品采用价格变动提醒：第一次成功采样只建立价格基线；之后价格上涨或下降都会发送邮件，价格未变则不发送。取消星标后，该商品恢复阈值提醒。星标状态保存在 `data/starred_products.json`，不会因切换星标而自动运行价格监控。

每次成功查询都会向 `data/price_history.json` 写入原始观测，例如：

```json
{
  "timestamp": "2026-08-28T10:37:21+08:00",
  "price": 50.5,
  "cluster_id": "10000008690",
  "product_id": "10000008690",
  "product_type": "resell",
  "product_name": "FuRyu 泡面压 澄闪 现货",
  "url": "https://mall.bilibili.com/neul-next/resell/detail.html?clusterId=10000008690&noTitleBar=1"
}
```

历史时间和统计均使用 `Asia/Shanghai`（UTC+8），仅保留滚动 30 天内的记录。记录按 `product_type + product_id + timestamp` 去重；如果 JSON 历史文件不存在，存储模块会尝试从旧版 `data/prices.db` 迁移。`src/storage.py` 还提供按商品统计小时或日最高价、最低价和均价的函数，各时间桶采用左闭右开区间，统计不会混入其他商品。

邮件收件地址及 SMTP 主机、端口、用户名在 `config/products.yaml` 的 `email` 下配置。当前使用 QQ SMTP（`smtp.qq.com:465`），配置中已填写收件地址。SMTP 密码必须放在本仓库的 Actions Secret `SMTP_PASSWORD` 中，不能写入 YAML 或代码。`email.to` 留空时会跳过发送。

## GitHub Actions 与 Dashboard

在 **Actions → Bilibili 商品价格监控 → Run workflow** 手动执行监控。工作流使用 Ubuntu 和 Python 3.12，先安装依赖、运行 `pytest`，再执行 `src.main` 并提交价格历史。监控按 `price-monitor-data` 串行运行，开始时检出所选分支的最新版本。若推送历史时遇到远端更新，`src.git_sync` 会变基并按商品与时间合并记录，最多尝试推送三次；没有变化时不会创建空提交。

公开价格面板：<https://dramingling.github.io/personal_documents/Bilibili_Goods_Price_Monitor/>

监控工作流成功完成后，**Sync Price Dashboard** 会把本仓库的 `data/price_history.json` 发布到 `DRAMINGLING/dramingling.github.io` 仓库 `main` 分支的 `personal_documents/Bilibili_Goods_Price_Monitor/data/price_history.json`。也可手动运行同步工作流。同步只复制价格数据，不采集价格，也不复制网页文件。跨仓库发布需要设置 Actions Secret `UPDATE_PRICE_HISTORY`，建议使用仅对目标仓库授予 **Contents: Read and write** 权限的 Fine-grained personal access token。

数据流：

```text
Bilibili 市集接口 → 价格监控工作流 → data/price_history.json
                                      └→ Sync Price Dashboard → GitHub Pages 数据文件
价格面板 ↔ Cloudflare Worker ↔ data/starred_products.json
```

## 星标 Worker 配置

`worker/src/index.js` 提供星标 API；`worker/wrangler.toml` 配置目标仓库、分支和允许访问的网页来源。Worker 通过 GitHub Contents API 读写 `data/starred_products.json`：读取列表无需密钥，更新列表需要 `STAR_API_KEY`。GitHub Token 和 API 密钥只保存在 Cloudflare Worker Secrets 中，不要写进仓库或网页。

可在 Cloudflare 控制台通过 Workers Builds 部署：连接本仓库的 `main` 分支，Root directory 设为 `worker`，Build command 留空；然后在 Worker 的 **Settings → Variables and Secrets** 中添加：

- `GITHUB_TOKEN`：Fine-grained personal access token，仅授予本仓库 **Contents: Read and write** 权限。
- `STAR_API_KEY`：单独生成的随机密钥，不要复用 GitHub Token。

`MONITOR_REPOSITORY`、`MONITOR_BRANCH` 和 `ALLOWED_ORIGIN` 已写在 `worker/wrangler.toml`。部署后，把 Worker 的 `/stars` 地址填入 Pages 仓库网页的 `CONFIG.starApiUrl`。首次操作星标时，在页面输入 `STAR_API_KEY`；密钥仅保留在当前标签页会话中。星标状态更新不会触发 Actions；要查询星标商品的新价格，仍需手动运行监控工作流。

