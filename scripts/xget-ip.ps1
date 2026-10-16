$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONIOENCODING = 'utf-8'
# Keep gh's existing login while Python isolates its own configuration.
if (-not $env:GH_CONFIG_DIR) {
    if ($env:XDG_CONFIG_HOME) { $env:GH_CONFIG_DIR = Join-Path $env:XDG_CONFIG_HOME 'gh' }
    elseif ($env:APPDATA) { $env:GH_CONFIG_DIR = Join-Path $env:APPDATA 'GitHub CLI' }
}
$pythonPath = 'C:\Users\yogur\Documents\Codex\.codex-python-env\Scripts\python.exe'
$enginePath = Join-Path $PSScriptRoot 'xget-preferred-ip.py'

function Show-DownloadResult($result) {
    Write-Host ('  地址：{0}（IPv{3}）    速度：{1} MiB/s    用时：{2} 秒' -f $result.connected_ip, $result.MiB_s, $result.seconds, $result.ip_version)
    if ($result.exit_ip) {
        Write-Host ('  出口：{0} / {1}    实际入口：{2}    Worker：{3}' -f $result.exit_ip, $result.country, $result.colo, $result.placement)
    }
}

function Get-RegionName($region) {
    $names = @{ hk = '香港'; sg = '新加坡'; jp = '日本'; tw = '台湾' }
    if ($names.ContainsKey([string]$region)) { return $names[[string]$region] }
    return $region
}

function Show-XgetEvent($event) {
    if ($event.worker_round) {
        $name = Get-RegionName $event.region
        if ($event.error) {
            Write-Host ('[Worker 第 {0} 轮未通过] {1}：{2}' -f $event.worker_round, $name, $event.error) -ForegroundColor DarkYellow
        } else {
            Write-Host ('[Worker 第 {0} 轮] {1}：{2} MiB/s，执行位置 {3}' -f $event.worker_round, $name, $event.MiB_s, $event.placement)
        }
    } elseif ($event.worker_ranking) {
        Write-Host "`n四地 Worker 排名：" -ForegroundColor Cyan
        foreach ($row in $event.worker_ranking) {
            $qualified = if ($row.eligible) { '合格' } else { '淘汰' }
            Write-Host ('  {0}：{1}，成功 {2}/{3}，最低 {4}，中位 {5} MiB/s' -f (Get-RegionName $row.ip), $qualified, $row.successes, $row.rounds, $row.minimum_MiB_s, $row.median_MiB_s)
        }
    } elseif ($event.worker_selected) {
        Write-Host ('最佳 Worker：{0}' -f (Get-RegionName $event.worker_selected)) -ForegroundColor Cyan
        if ($event.dry_run) { Write-Host '本次只测速，未切换默认 Worker。' }
    } elseif ($event.worker_deploy) {
        Write-Host ('[部署默认地区] {0}：{1} {2}' -f (Get-RegionName $event.worker_deploy), $event.status, $event.conclusion)
        if ($event.url) { Write-Host $event.url }
    } elseif ($event.worker_wait) {
        Write-Host ('[等待部署传播] 目标 {0}，当前请求仍使用 {1}，稍后复验。' -f (Get-RegionName $event.worker_wait), (Get-RegionName $event.observed_region))
    } elseif ($event.worker_restored) {
        Write-Host ('[恢复默认地区] {0}' -f (Get-RegionName $event.worker_restored)) -ForegroundColor Yellow
    } elseif ($event.stage -eq 'refresh') {
        switch ($event.status) {
            'updated' { Write-Host ('[候选更新] {0}：取得 {1} 个地址' -f $event.region, $event.count) -ForegroundColor Green }
            'fallback' { Write-Host ('[使用本地] {0}：保留 {1} 个地址；{2}' -f $event.region, $event.count, $event.reason) -ForegroundColor Yellow }
            'local' { Write-Host ('[使用本地] {0}：{1} 个地址' -f $event.region, $event.count) }
        }
        if ($event.saved) { Write-Host '[候选更新] 已保存，下次拉取失败可使用本地列表。' }
        if ($event.warning) { Write-Host ('[保存失败] 本次继续测速；{0}' -f $event.reason) -ForegroundColor Yellow }
    } elseif ($event.stage -eq 'screen') {
        if ($event.error) {
            Write-Host ('[初筛未通过] {0} / {1}：{2}' -f $event.ip, $event.source_region, $event.error) -ForegroundColor DarkYellow
        } else {
            Write-Host ('[初筛通过] {0} / {1}，实际入口 {2}，{3} MiB/s' -f $event.ip, $event.source_region, $event.colo, $event.MiB_s) -ForegroundColor Green
        }
    } elseif ($event.round) {
        if ($event.error) {
            Write-Host ('[第 {0} 轮未通过] {1}：{2}' -f $event.round, $event.ip, $event.error) -ForegroundColor DarkYellow
        } else {
            Write-Host ('[第 {0} 轮] {1}：{2} MiB/s' -f $event.round, $event.ip, $event.MiB_s)
        }
    } elseif ($event.ranking) {
        Write-Host "`n复测排名（先看全部成功，再看最低速度和中位速度）：" -ForegroundColor Cyan
        foreach ($row in $event.ranking) {
            $qualified = if ($row.eligible) { '合格' } else { '淘汰' }
            Write-Host ('  {0,-16} {1}，成功 {2}/{3}，最低 {4}，中位 {5} MiB/s' -f $row.ip, $qualified, $row.successes, $row.rounds, $row.minimum_MiB_s, $row.median_MiB_s)
        }
    } elseif ($event.selected) {
        Write-Host ('最佳候选：{0}' -f $event.selected.ip) -ForegroundColor Cyan
        if ($event.dry_run) { Write-Host '本次只测速，没有修改固定 IP。' }
    } elseif ($event.verified) {
        Write-Host '[验证成功] 当前固定地址、CN 出口、所选地区 Worker 和分段下载均正常。' -ForegroundColor Green
        Show-DownloadResult $event.verified
    } elseif ($event.network) {
        Write-Host ('当前解析：{0}' -f ($event.resolved -join ', ')) -ForegroundColor Cyan
        Show-DownloadResult $event.network
    } elseif ($event.preflight) {
        Write-Host '[切换前验证通过]' -ForegroundColor Green
        Show-DownloadResult $event.preflight
    } elseif ($event.baseline) {
        Write-Host ('当前出口：{0} / {1}；入口：{2}' -f $event.baseline.exit_ip, $event.baseline.country, $event.baseline.colo)
    } elseif ($event.candidate_count) {
        Write-Host ('开始初筛 {0} 个候选。地区标签仅供参考，以实际入口为准。' -f $event.candidate_count)
    } elseif ($event.shortlist) {
        Write-Host ('开始三轮复测：{0}' -f ($event.shortlist -join ', ')) -ForegroundColor Cyan
    } elseif ($event.backup) {
        Write-Host ('原 hosts 备份：{0}' -f $event.backup)
    } elseif ($event.elevation) {
        Write-Host '修改 hosts 需要管理员权限，请允许接下来出现的 Windows UAC 提示。' -ForegroundColor Yellow
    } elseif ($event.cleared) {
        Write-Host '已取消本机固定，恢复系统 DNS 解析。' -ForegroundColor Green
    } elseif ($event.rolled_back) {
        Write-Host '验证失败，已恢复本次修改前的 hosts。' -ForegroundColor Yellow
    } elseif ($event.warning) {
        Write-Host ('提示：{0} {1}' -f $event.warning, $event.detail) -ForegroundColor Yellow
    } elseif ($event.error) {
        Write-Host ('操作未完成：{0}' -f $event.error) -ForegroundColor Red
    }
}

function Invoke-Xget([string[]]$EngineArguments) {
    Write-Host ''
    & $pythonPath -u $enginePath @EngineArguments 2>&1 | ForEach-Object {
        $line = [string]$_
        try { $event = $line | ConvertFrom-Json -ErrorAction Stop }
        catch { Write-Host $line; return }
        Show-XgetEvent $event
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host '操作未完成，请查看上方原因。可返回菜单重试。' -ForegroundColor Red
    } else {
        Write-Host "`n操作完成。" -ForegroundColor Green
    }
}

function ConvertTo-IP([string]$Value) {
    $value = $Value.Trim().TrimStart('[').TrimEnd(']')
    $parsed = $null
    if (($value.Contains(':') -or $value -match '^\d{1,3}(\.\d{1,3}){3}$') -and [System.Net.IPAddress]::TryParse($value, [ref]$parsed)) {
        return $parsed.ToString()
    }
    return $null
}

function Read-IP([string]$Prompt) {
    $value = ConvertTo-IP (Read-Host $Prompt)
    if ($value) { return $value }
    Write-Host '请输入有效的 IPv4 或 IPv6 地址，不需要端口。' -ForegroundColor Yellow
    return $null
}

try {
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw "找不到运行环境：$pythonPath" }
    if (-not (Test-Path -LiteralPath $enginePath)) { throw "找不到测速脚本：$enginePath" }
    while ($true) {
        Write-Host "`n========== Xget IP 与 Worker 优选 ===========" -ForegroundColor Cyan
        Write-Host '域名：xget.qyqq.wang | IPv4 / IPv6 混合测速 | CN 出口 | 香港 / 新加坡 / 日本 / 台湾 Worker'
        Write-Host '  1. 更新 IP 候选、测速 IP 和四地 Worker 并自动切换（默认）'
        Write-Host '  2. 更新候选并测试 IP 和四地 Worker，不切换'
        Write-Host '  3. 查看当前地址并验证下载'
        Write-Host '  4. 手动固定到指定 IP'
        Write-Host '  5. 取消固定，恢复系统 DNS'
        Write-Host '  6. 比较自己输入的几个 IP'
        Write-Host '  0. 退出'
        $choice = (Read-Host '请选择 [默认 1]').Trim()
        if ($choice -eq '') { $choice = '1' }
        if ($choice -eq '0') { break }
        try {
            switch ($choice) {
                '1' { Invoke-Xget @('auto') }
                '2' { Invoke-Xget @('auto', '--dry-run') }
                '3' { Invoke-Xget @('status') }
                '4' {
                    $address = Read-IP '输入要固定的 IP'
                    if ($address) { Invoke-Xget @('set', $address, '--elevate') }
                }
                '5' { Invoke-Xget @('clear', '--elevate') }
                '6' {
                    $values = (Read-Host '输入候选 IPv4 / IPv6 地址，用空格或逗号分隔').Trim() -split '[,，\s]+'
                    $valid = $values.Count -gt 0
                    foreach ($value in $values) {
                        $normalized = ConvertTo-IP $value
                        if (-not $normalized) { $valid = $false }
                    }
                    if ($valid) { Invoke-Xget (@('test') + $values) }
                    else { Write-Host '地址格式不正确，未开始测速。' -ForegroundColor Yellow }
                }
                default { Write-Host '请选择菜单中的数字。' -ForegroundColor Yellow }
            }
        } catch {
            Write-Host ('操作未完成：{0}' -f $_.Exception.Message) -ForegroundColor Red
        }
        $null = Read-Host '按回车返回菜单'
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    $null = Read-Host '按回车关闭'
    exit 1
}
