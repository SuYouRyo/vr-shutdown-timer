# 一键打包
#
#   pwsh -File build.ps1                  # 只打包单文件 exe
#   pwsh -File build.ps1 -Portable        # 只打包便携目录版
#   pwsh -File build.ps1 -All             # 单文件 + 便携目录版
#   pwsh -File build.ps1 -Installer       # 便携目录版 + Windows 安装包
#   pwsh -File build.ps1 -All -Installer -Clean   # 全部，先清理
#
# 产物:
#   dist\VRShutdownTimer.exe                        单文件（启动时自解压到 %TEMP%）
#   dist_portable\VRShutdownTimer\                  便携目录版（不依赖 %TEMP%）
#   dist_installer\VRShutdownTimer-Setup-<版本>.exe 安装包（图形安装 + 卸载）
#   dist_installer\uninstall.exe                    卸载器（已打进安装包）
#
# 注意：务必用 .spec 文件打包。若用 `pyinstaller --name VRShutdownTimer main.py`，
# PyInstaller 会自动生成同名 spec 覆盖仓库里的 spec，并变成 onedir 模式。

param(
    [switch]$Clean,
    [switch]$Portable,
    [switch]$All,
    [switch]$Installer
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not $Portable -and -not $All -and -not $Installer) { $doOnefile = $true }
if ($Portable -or $All -or $Installer) { $doPortable = $true }

Write-Host '==> 生成图标与版本资源' -ForegroundColor Cyan
python tools/make_icon.py
python tools/make_version_info.py

if (-not (Test-Path -LiteralPath 'assets\app.ico')) {
    throw 'assets\app.ico 缺失：spec 文件依赖它，构建会失败'
}

if ($Clean) {
    Write-Host '==> 清理旧产物' -ForegroundColor Cyan
    Remove-Item -Recurse -Force build, dist, build_portable, dist_portable, build_installer, dist_installer -ErrorAction SilentlyContinue
}

if ($doOnefile) {
    Write-Host '==> 打包单文件版' -ForegroundColor Cyan
    python -m PyInstaller --noconfirm --clean --distpath dist --workpath build VRShutdownTimer.spec
    $exe = Join-Path $PSScriptRoot 'dist\VRShutdownTimer.exe'
    if (Test-Path -LiteralPath $exe) {
        $size = [math]::Round((Get-Item -LiteralPath $exe).Length / 1MB, 1)
        Write-Host ("==> 完成: {0} ({1} MB)" -f $exe, $size) -ForegroundColor Green
    } else {
        throw '打包失败：未找到 dist\VRShutdownTimer.exe'
    }
}

if ($doPortable) {
    Write-Host '==> 打包便携目录版' -ForegroundColor Cyan
    # 必须显式指定 --distpath：spec 里的 COLLECT 不带路径，PyInstaller 默认输出到
    # dist\，会和单文件版混在一起（旧脚本就是这么错的，之后再也找不到便携版）。
    python -m PyInstaller --noconfirm --clean --distpath dist_portable --workpath build_portable VRShutdownTimer-portable.spec
    $dir = Join-Path $PSScriptRoot 'dist_portable\VRShutdownTimer'
    if (Test-Path -LiteralPath (Join-Path $dir 'VRShutdownTimer.exe')) {
        $sum = (Get-ChildItem -LiteralPath $dir -Recurse -File | Measure-Object -Property Length -Sum).Sum
        Write-Host ("==> 完成: {0} ({1} MB)" -f $dir, [math]::Round($sum / 1MB, 1)) -ForegroundColor Green
    } else {
        throw '打包失败：未找到 dist_portable\VRShutdownTimer\VRShutdownTimer.exe'
    }
}

if ($Installer) {
    Write-Host '==> 打包 Windows 安装包' -ForegroundColor Cyan
    python installer/build_installer.py
    if ($LASTEXITCODE -ne 0) { throw '安装包构建失败' }
    $setup = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'dist_installer') -Filter 'VRShutdownTimer-Setup-*.exe' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($setup) {
        Write-Host ("==> 完成: {0} ({1} MB)" -f $setup.FullName, [math]::Round($setup.Length / 1MB, 1)) -ForegroundColor Green
    } else {
        throw '打包失败：未找到 dist_installer\VRShutdownTimer-Setup-*.exe'
    }
}
