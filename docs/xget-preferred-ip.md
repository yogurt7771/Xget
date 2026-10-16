# Xget 优选入口

本机优选工具已独立到 `I:\Codes\Proxy\Cloudflare-Preferred-IP`，与 Google
Drive 共用测速、候选刷新和回滚逻辑。

双击 `scripts/xget-ip.cmd` 或
`scripts/xget-auto-ip.cmd`，进入全部服务的同步优选菜单，无需参数。也可双击上级独立项目中的
`优选IP.cmd`，直接同步全部服务，无需选择服务。

完整说明见
[统一工具 README](../../Cloudflare-Preferred-IP/README.md)。候选在独立项目的
`candidates.json`，服务配置在 `services.json`。本项目 `xget-preferred-ip.py`
与 PowerShell 文件仅作为兼容入口。

## Cloudflare 部署

本项目继续持有
`src/region-router.js`、`src/regional-worker.js`、`scripts/deploy-regions.mjs`
和 `scripts/worker-regions.json`，独立工具不复制业务代码或部署密钥。

四个 Worker 为 `xget-hk`、`xget-sg`、`xget-jp`、`xget-tw`，统一入口为
`xget`。统一工具联合测速后同步各服务的默认地区，Xget 通过 fork 的 GitHub
Actions 切换，正常 `/hf/...` 地址不变。`/__xget/status`
查看默认地区；`/__xget/regions/{hk|sg|jp|tw}/hf/...` 指定测试地区。

部署提示：香港 `aws:ap-east-1`、新加坡 `aws:ap-southeast-1`、日本
`gcp:asia-northeast1`、台湾 `gcp:asia-east1`。测速时核对 Worker
trace 出站数据中心；入口城市与 Worker 出站位置分开显示。

## 日本地区验证（2026-10-16）

线上原 AWS 东京 Placement 配置存在，但 trace 持续观测到 SJC。更换为 Google 东京参照后，固定入口
`104.17.145.145`、CN 出口 `112.80.170.237`，三轮 512 MiB 均观测到 NRT。

| 轮次 |  MiB/s | 内容验证                               |
| ---- | -----: | -------------------------------------- |
| 1    | 23.504 | 206、完整 Range、SHA256 与此前分段一致 |
| 2    | 32.467 | 同上                                   |
| 3    | 19.216 | 同上                                   |

三轮没有 5 秒零进度窗口。中位 23.504 MiB/s、最低 19.216
MiB/s。验证时默认地区保持新加坡；这组顺序测试不是与其他地区同时重测的结果。Cloudflare 内部将原参照调到 SJC 的原因尚无法确认。
