[CmdletBinding()]
param(
    [string]$Python = $(if ($env:ARNOLD_PY) { $env:ARNOLD_PY } else { ".\.venv\Scripts\python.exe" }),
    [switch]$ForceBinaries
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = if ([IO.Path]::IsPathRooted($Python)) { $Python } else { Join-Path $repoRoot $Python }
$pythonPath = (Resolve-Path $pythonPath).Path
$distPath = Join-Path $repoRoot "dist"
$env:PYTHONUTF8 = "1"

Push-Location $repoRoot
try {
    $versionOutput = & $pythonPath -c "from arnold_dw import __version__; print(__version__)"
    if ($LASTEXITCODE -ne 0) { throw "Could not read arnold_dw.__version__." }
    $version = ($versionOutput | Select-Object -Last 1).Trim()
    if (-not $version -or $version -notmatch '^[0-9A-Za-z.+!-]+$') { throw "Invalid application version: $version" }

    $fetchArgs = @((Join-Path $repoRoot "tools/fetch_binaries.py"))
    if ($ForceBinaries) { $fetchArgs += "--force" }
    & $pythonPath @fetchArgs
    if ($LASTEXITCODE -ne 0) { throw "Fetching runtime binaries failed." }

    & $pythonPath -m PyInstaller --noconfirm --distpath $distPath --workpath (Join-Path $repoRoot "build") (Join-Path $repoRoot "packaging/ArnoldDW.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $appDirectory = Join-Path $distPath "Arnold DW"
    $appExecutable = Join-Path $appDirectory "Arnold DW.exe"
    if (-not (Test-Path -LiteralPath $appExecutable)) { throw "PyInstaller output not found: $appExecutable" }

    $zipPath = Join-Path $distPath "ArnoldDW-$version-win64.zip"
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $appDirectory "*") -DestinationPath $zipPath -CompressionLevel Optimal
    $zipSize = (Get-Item -LiteralPath $zipPath).Length
    $installSize = (Get-ChildItem -LiteralPath $appDirectory -File -Recurse | Measure-Object -Property Length -Sum).Sum

    $iscc = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $innoCandidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Inno Setup 6\ISCC.exe"
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
        if ($innoCandidates) { $iscc = $innoCandidates | Select-Object -First 1 }
    }

    if ($iscc) {
        $installerScript = Join-Path $repoRoot "packaging/installer.iss"
        & $iscc "/DAppVersion=$version" "/DSourceDir=$appDirectory" "/DOutputDir=$distPath" $installerScript
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
        $setupPath = Join-Path $distPath "ArnoldDW-$version-setup.exe"
        if (-not (Test-Path -LiteralPath $setupPath)) { throw "Inno Setup output not found: $setupPath" }
        $setupSize = (Get-Item -LiteralPath $setupPath).Length
    }
    else {
        Write-Warning "Inno Setup 6 was not found; portable ZIP was built, installer skipped."
    }

    Write-Host "Build complete: $zipPath"
    Write-Host "Installed files: $installSize bytes; portable ZIP: $zipSize bytes"
    if ($setupPath) { Write-Host "Installer complete: $setupPath ($setupSize bytes)" }
}
finally {
    Pop-Location
}
