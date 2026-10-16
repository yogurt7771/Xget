# Xget 一键选择入口 IP 和 Worker 地区

双击 `scripts/xget-ip.cmd`，在中文菜单直接回车：自动更新 IPv4 /
IPv6 候选，测速入口 IP，再比较香港、新加坡、日本、台湾四个 Worker，切换到本次表现最稳定、最快的组合。`scripts/xget-auto-ip.cmd`
也是同一个入口，无需命令参数。

## 菜单

| 选项      | 功能                                      |
| --------- | ----------------------------------------- |
| 1（默认） | 更新候选，测速 IP 和四地 Worker，自动切换 |
| 2         | 同样测速，只显示结果，不切换              |
| 3         | 查看当前地址并验证下载                    |
| 4         | 输入 IPv4 或 IPv6，手动固定本机入口       |
| 5         | 取消本机固定，恢复系统 DNS                |
| 6         | 输入多个 IPv4 / IPv6，只比较这些入口地址  |
| 0         | 退出                                      |

CMD 只负责双击启动，PowerShell 显示交互菜单，Python 执行测速、验证和备份。操作结束后窗口保留结果，回车返回菜单。修改 hosts 时会出现 Windows
UAC 提示；取消授权不修改文件。

## 两层选择

- **入口 IP**：修改这台电脑的 hosts，只影响本机访问 `xget.qyqq.wang`
  的目标地址；IPv4、IPv6 一起比较。候选来源的地区标签不保证实际入口城市，实际入口以
  `/cdn-cgi/trace` 为准。
- **Worker 地区**：Cloudflare 同时保留
  `xget-hk`、`xget-sg`、`xget-jp`、`xget-tw` 四个服务。统一入口 `xget`
  将正常下载交给选中的服务。切换默认地区通过已登录的 GitHub
  CLI 触发 fork 的部署工作流，会影响这个域名的所有用户。

工具不修改 sing-box 的 CN 路由或 Cloudflare DNS，不读取 HF
token。IPv4 和 IPv6 的公网出口地址本来就不同，因此分别建立 CN 出口基准，同一地址族测速及切换前后必须保持相同出口。

地区配置保存在 `scripts/worker-regions.json`。使用 Cloudflare
Placement 的区域提示：香港 `aws:ap-east-1`、新加坡 `aws:ap-southeast-1`、日本
`aws:ap-northeast-1`、台湾
`gcp:asia-east1`。提示指定靠近该云区域的 Cloudflare 执行位置；测速请求让目标 Worker 向 Cloudflare
trace 发起子请求，以返回的出站数据中心核对地区（`trace-HKG`
等）；日常下载不增加这次探测。它观察的是 Worker 出站位置，不是用户入口城市，不能只凭配置名称认定地区。

## 测速与切换规则

1. 在线刷新 IP 候选；某组拉取失败或没有有效地址，就使用该组本地列表。加入当前地址及已知可用的备用地址。
2. 每个 IP 先验证 CN 出口，再通过当前默认 Worker 下载真实模型的 1
   MiB 分段；单个请求最多 12 秒。
3. 最快四个 IP 加上初筛通过的当前地址，交错进行三轮 4
   MiB 下载。仅三轮全部成功且内容哈希一致者合格。先比较最低速度，再比较中位速度，完全相同时保留当前地址。
4. 固定获选 IP，刷新 DNS，通过正常域名下载验证地址、出口、Worker 地区、206
   Range 和内容哈希；失败恢复 hosts。
5. 在获选 IP 上对四地 Worker 各进行三轮 4
   MiB 下载，采用相同的稳定性与速度规则；完全相同时保留现有地区。
6. 若默认地区需要改变，等待 GitHub
   Actions 部署统一入口。随后通过正常下载路径验证所选地区和内容；部署或验证失败时尝试恢复之前的默认地区，并报告恢复结果。四个地区服务始终保留。

只测速模式不修改 hosts 或部署。手动 IP 操作不会改变默认 Worker。自动流程先确定入口、再确定 Worker，是分阶段比较，不是穷举所有 IP 与地区组合；结果只代表当时样本，不能保证长期或全网最优。运行前暂停其他大流量下载。

测速始终使用 `xget.qyqq.wang` 的 TLS 域名，候选 IP 用 `curl --resolve`
临时指定。模型为公开的
`SmilingWolf/wd-eva02-large-tagger-v3/model.msgpack`，偏移 1 MiB。四地测试路径为
`/__xget/regions/{hk|sg|jp|tw}/hf/...`，日常下载继续使用原来的 `/hf/...`
地址。`/__xget/status` 返回当前默认地区。

## 候选更新

候选保存在 `scripts/xget-ip-candidates.json`，每次菜单 1、2 测速前自动刷新：

- IPv4：[CloudflareIP 数据](https://github.com/gslege/CloudflareIP/blob/main/country.txt)，按来源中的 HK、SG、JP、TW 标签拆分；缺少地区时保留本地候选。
- IPv6：[IPDB 数据](https://github.com/ymyuuu/IPDB/blob/main/BestCF/bestcfv6.txt)，没有可靠地区标签，按实际连通与下载表现比较。
- 本地台湾入口候选 `104.16.0.132`
  来自历史记录，不保证台湾接入。它与独立部署的台湾 Worker 是两回事。

相同 URL 一次只拉取一次，连接超时 5 秒、总超时 15 秒。拒绝 HTML 错误页、错误端口及无效地址，规范化去重。成功列表保存本地；网络或解析失败按组回退。日志的“更新”代表取得发布方列表，不保证发布方刚刚更新过数据。

## 备份、环境与部署

hosts 修改前保存为原文件旁的
`hosts.xget-backup-时间戳`，保留其他域名记录，检测并发修改。候选列表覆盖前备份到 Python 工具环境临时目录。不要强制结束正在写入或恢复的进程。

运行依赖本机现有的 Codex Python 工具环境、curl、GitHub
CLI。Worker 自动切换需要 GitHub CLI 已登录且能运行 `yogurt7771/Xget`
的部署工作流；Cloudflare 凭据仅保存在 GitHub Actions secrets 中。

部署由 `.github/workflows/workers.yml` 调用
`scripts/deploy-regions.mjs`。全量部署先部署四个地区服务，再更新统一入口；普通代码更新保留线上已选地区。自动测速切换仅部署入口的默认地区，不重新部署四个服务。

更换后重启下载任务，使新连接使用新地址。本工具验证公开模型的分段下载，不代表整个模型完成或私有模型权限验证。
