$ErrorActionPreference = 'Stop'
$entry = 'I:\Codes\Proxy\Cloudflare-Preferred-IP\preferred-ip.ps1'
if (-not (Test-Path -LiteralPath $entry)) {
    Write-Host "找不到统一优选工具：$entry" -ForegroundColor Red
    $null = Read-Host '按回车关闭'
    exit 1
}
& $entry
