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

价格记录存放在 SQLite 数据库 `data/prices.db`。工作流在成功查询后提交该数据库，使历史记录可在后续定时运行中保留。

## 配置邮件

在 `config/products.yaml` 填写 `email.to`、SMTP 主机、端口和用户名；将 SMTP 密码设置为仓库的 `SMTP_PASSWORD` Secret。密码绝不能提交到 YAML、代码或 Git 历史中。

可从 Actions 页面使用 **Run workflow** 手动执行。
