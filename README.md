# Bilibili 商品价格监控

该项目每 30 分钟通过 GitHub Actions 查询 Bilibili 会员购转售商品，并在价格满足条件时发送邮件提醒。

## 当前监控项
* 澄闪（ID: 10000008690）：价格小于或等于 `45` 元。
* 小司（ID: 10000001234）：价格小于或等于 `45` 元。
* 唯（ID: 10000000940）：价格小于或等于 `55` 元。
* 阿梓喵（ID: 10000001118）：价格小于或等于 `55` 元。
* 波奇（ID: 10000009511）：价格小于或等于 `70` 元。
* 提醒邮箱已在配置中设置；SMTP 密码仍必须通过 `SMTP_PASSWORD` Secret 提供。

## 工作方式与边界

`BilibiliFetcher` 使用市集公开 JSON 详情接口 `mall-search-items/items_detail/cluster_info`，以 `clusterId` 作为参数读取 `data.clusterPriceFloorVO.priceTag.firstPrice`，而非从动态 HTML 中猜测金额。若接口要求登录、验证码、拒绝访问，或响应不含该明确最低价字段，程序会失败并把原因显示在 Actions 日志中；项目不会尝试绕过这些限制。

可在任意商品配置中设置 `enabled: false`，临时停用已经下架或接口不再可用的商品。被停用的商品会在日志中明确显示为“跳过”，不会被视为一次成功的价格检查。取得新的有效商品链接后，更新 `url`、`cluster_id` 并删除（或改为 `true`）该字段即可重新启用。

## 价格历史与可视化

每一次成功查询都会追加一条原始观测到 `data/price_history.json`，而不是保存预先聚合的数值。例如：

```json
{
  "timestamp": "2026-08-28T10:37:21+08:00",
  "price": 45.5,
  "cluster_id": "10000008690",
  "url": "https://mall.bilibili.com/..."
}
```

时间戳和所有统计都使用 `Asia/Shanghai`（UTC+8），不会依赖 GitHub runner 的系统时区。历史只保留最近 **3 个自然月**：清理时从当前东八区时间减三个月，并在目标月不存在该日期时安全地钳制到月末（不是简单减 90 天）。仓库旧的 `data/prices.db` 会在 JSON 文件首次缺失时被尽力读取并迁移；无法解析的旧行会被安全跳过。

工作流在成功取得每个商品价格后写入原始记录，再从原始记录计算统计。小时桶严格为 `[HH:00, HH+1:00)`，日桶严格为 `[00:00, 次日 00:00)`；所以右边界的记录属于下一个桶。每个桶的最高价、最低价和均价分别是该桶所有实际成功采样价格的 `max`、`min` 和算术平均值，绝不使用其他桶的值。中间没有成功采样的小时或日期输出 `null`，图表显示为缺口而不是 0。

`docs/index.html` 是轻量的静态 Chart.js 折线图（可通过 GitHub Pages 发布）。页面中可独立切换 **按小时/按天** 横轴及 **最高价/最低价/均价** 纵轴；悬停会显示东八区时间和具体人民币价格，纵轴单位为“价格（元）”。聚合图表数据在 `docs/price_history.json`，仅为展示生成，可随时由原始记录重建。

## Actions 写入一致性

价格写入 job 使用 `concurrency.group: price-monitor-data` 且 `cancel-in-progress: false`，并授予最小的 `contents: write` 权限。写入前会根据运行时分支执行 `git fetch origin` 和 `git pull --rebase origin <branch>`；不会硬编码分支名。提交阶段最多推送 3 次。若 push 被拒绝，脚本保存本次原始记录、获取远程最新提交并重置到远程状态，将远程记录和本地记录按 `timestamp + price + cluster_id + url` 去重合并、按时间排序、清理过期项并重新生成图表后再次提交。这样不会用 `ours`/`theirs` 丢弃合法的价格观测；没有文件变化时不会创建空提交。

## 配置邮件

在 `config/products.yaml` 填写 `email.to`、SMTP 主机、端口和用户名；将 SMTP 密码设置为仓库的 `SMTP_PASSWORD` Secret。密码绝不能提交到 YAML、代码或 Git 历史中。

可从 Actions 页面使用 **Run workflow** 手动执行。
