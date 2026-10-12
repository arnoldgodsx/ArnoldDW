[CmdletBinding()]
param(
    [string]$Python = $(if ($env:ARNOLD_PY) { $env:ARNOLD_PY } else { ".\.venv\Scripts\python.exe" }),
    [switch]$ForceBinaries,
    # Fail instead of warning when Inno Setup is missing (release and CI builds).
    [switch]$RequireInstaller,
    # Also produce the portable ArnoldDW-<version>-win64.zip.
    [switch]$Portable
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

    $installSize = (Get-ChildItem -LiteralPath $appDirectory -File -Recurse | Measure-Object -Property Length -Sum).Sum
    Write-Host "Largest files in the app folder:"
    Get-ChildItem -LiteralPath $appDirectory -File -Recurse | Sort-Object Length -Descending | Select-Object -First 25 |
        ForEach-Object { "{0,8:N1} MB  {1}" -f ($_.Length / 1MB), $_.FullName.Substring($appDirectory.Length + 1) } | Write-Host
    $internal = Join-Path $appDirectory "_internal"
    Write-Host "Size by top-level entry under _internal:"
    Get-ChildItem -LiteralPath $internal | ForEach-Object {
        $size = if ($_.PSIsContainer) { (Get-ChildItem -LiteralPath $_.FullName -File -Recurse | Measure-Object -Property Length -Sum).Sum } else { $_.Length }
        [pscustomobject]@{ Name = $_.Name; Size = $size }
    } | Sort-Object Size -Descending | Select-Object -First 25 |
        ForEach-Object { "{0,8:N1} MB  {1}" -f ($_.Size / 1MB), $_.Name } | Write-Host

    if ($Portable) {
        $zipPath = Join-Path $distPath "ArnoldDW-$version-win64.zip"
        if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
        Compress-Archive -Path (Join-Path $appDirectory "*") -DestinationPath $zipPath -CompressionLevel Optimal
        $zipSize = (Get-Item -LiteralPath $zipPath).Length
    }

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
        # The wizard's agreement page shows the disclaimer. Inno Setup reads plain-text
        # files as UTF-8 only with a BOM, so write a BOM'd copy for the Turkish text.
        $licenseFile = Join-Path $repoRoot "build/LICENSE-AGREEMENT.txt"
        New-Item -ItemType Directory -Force -Path (Split-Path $licenseFile) | Out-Null
        $disclaimer = Get-Content -Raw -Encoding UTF8 (Join-Path $repoRoot "DISCLAIMER.md")
        [IO.File]::WriteAllText($licenseFile, $disclaimer, (New-Object Text.UTF8Encoding $true))
        & $iscc "/Qp" "/DAppVersion=$version" "/DSourceDir=$appDirectory" "/DOutputDir=$distPath" "/DLicenseFile=$licenseFile" $installerScript
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
        $setupPath = Join-Path $distPath "ArnoldDW-$version-setup.exe"
        if (-not (Test-Path -LiteralPath $setupPath)) { throw "Inno Setup output not found: $setupPath" }
        $setupSize = (Get-Item -LiteralPath $setupPath).Length
    }
    elseif ($RequireInstaller) {
        throw "Inno Setup 6 (ISCC.exe) was not found; install it or drop -RequireInstaller."
    }
    else {
        Write-Warning "Inno Setup 6 was not found; portable ZIP was built, installer skipped."
    }

    Write-Host ("Build complete: {0} ({1:N1} MB installed)" -f $appDirectory, ($installSize / 1MB))
    if ($zipPath) { Write-Host ("Portable ZIP: {0} ({1:N1} MB)" -f $zipPath, ($zipSize / 1MB)) }
    if ($setupPath) { Write-Host ("Installer complete: {0} ({1:N1} MB)" -f $setupPath, ($setupSize / 1MB)) }
}
finally {
    Pop-Location
}
