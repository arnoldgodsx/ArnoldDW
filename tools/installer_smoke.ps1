<#
.SYNOPSIS
    Installs, checks and uninstalls an Arnold DW setup.exe silently.

.DESCRIPTION
    Used by CI and before publishing a release. Installs for the current user
    into a temporary folder, checks the executable, shortcuts and the
    "Apps & features" entry, runs the first-launch component download
    (ffmpeg + Deno) headlessly, starts the app, then runs the uninstaller and
    checks that the install folder, components and registry entry are gone.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [string]$InstallDir = (Join-Path ([IO.Path]::GetTempPath()) "ArnoldDW-smoke")
)

$ErrorActionPreference = "Stop"
$appId = "{D9442C2D-5C16-4B2F-90D2-2D2E2E5298B7}_is1"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appId"
$setupPath = (Resolve-Path -LiteralPath $Setup).Path
$exe = Join-Path $InstallDir "Arnold DW.exe"
$uninstaller = Join-Path $InstallDir "unins000.exe"
$installLog = Join-Path ([IO.Path]::GetTempPath()) "ArnoldDW-install.log"

if (Test-Path -LiteralPath $InstallDir) { Remove-Item -LiteralPath $InstallDir -Recurse -Force }

Write-Host "Installing $setupPath -> $InstallDir"
$install = Start-Process -FilePath $setupPath -Wait -PassThru -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/TASKS=desktopicon",
    "/DIR=`"$InstallDir`"", "/LOG=`"$installLog`""
)
if ($install.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $installLog) { Get-Content -LiteralPath $installLog | Select-Object -Last 40 }
    throw "Setup exited with code $($install.ExitCode)"
}

foreach ($required in @($exe, $uninstaller, (Join-Path $InstallDir "_internal"))) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing after install: $required" }
}
if (-not (Test-Path -LiteralPath $uninstallKey)) { throw "Apps & features entry was not registered" }
$entry = Get-ItemProperty -LiteralPath $uninstallKey
Write-Host "Registered: $($entry.DisplayName) $($entry.DisplayVersion)"

$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Arnold DW\Arnold DW.lnk"
if (-not (Test-Path -LiteralPath $startMenu)) { throw "Start menu shortcut missing: $startMenu" }
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Arnold DW.lnk"
if (-not (Test-Path -LiteralPath $desktop)) { throw "Desktop shortcut missing: $desktop" }

$version = Start-Process -FilePath $exe -ArgumentList "--version" -Wait -PassThru
if ($version.ExitCode -ne 0) { throw "Installed exe --version exited with code $($version.ExitCode)" }

# First-launch components, exactly as the setup screen downloads them.
$runtimeDir = Join-Path $env:LOCALAPPDATA "Arnold DW\runtime"
if (Test-Path -LiteralPath $runtimeDir) { Remove-Item -LiteralPath $runtimeDir -Recurse -Force }
Write-Host "Downloading runtime components"
$watch = [Diagnostics.Stopwatch]::StartNew()
$components = Start-Process -FilePath $exe -ArgumentList "--install-components" -PassThru
if (-not $components.WaitForExit(600000)) { $components.Kill(); throw "Component download timed out" }
if ($components.ExitCode -ne 0) {
    $log = Get-ChildItem (Join-Path $env:APPDATA "Arnold DW\logs") -Filter *.log -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($log) { Get-Content -LiteralPath $log.FullName | Select-Object -Last 40 }
    throw "--install-components exited with code $($components.ExitCode)"
}
Write-Host ("Components installed in {0:N0} s" -f $watch.Elapsed.TotalSeconds)
foreach ($tool in @("ffmpeg\ffmpeg.exe", "ffmpeg\ffprobe.exe", "deno\deno.exe")) {
    $path = Join-Path $runtimeDir $tool
    if (-not (Test-Path -LiteralPath $path)) { throw "Component missing after install: $path" }
}
Get-Content -LiteralPath (Join-Path $runtimeDir "ffmpeg\component.json") | Write-Host
$ffmpegVersion = & (Join-Path $runtimeDir "ffmpeg\ffmpeg.exe") -version | Select-Object -First 1
Write-Host $ffmpegVersion
if ($ffmpegVersion -notmatch "ffmpeg version") { throw "Installed ffmpeg does not run" }
$denoVersion = & (Join-Path $runtimeDir "deno\deno.exe") --version | Select-Object -First 1
Write-Host $denoVersion
if ($denoVersion -notmatch "^deno ") { throw "Installed deno does not run" }

$app = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 8
$app.Refresh()
if ($app.HasExited) { throw "Installed app exited before the 8-second startup check" }

# The uninstaller must close the running app on its own.
Write-Host "Uninstalling (app still running)"
$uninstall = Start-Process -FilePath $uninstaller -Wait -PassThru -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
)
if ($uninstall.ExitCode -ne 0) { throw "Uninstaller exited with code $($uninstall.ExitCode)" }

# unins000.exe hands off to a temporary copy and returns early; wait for it to finish.
$deadline = (Get-Date).AddSeconds(60)
while ((Test-Path -LiteralPath $exe) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
while ((Test-Path -LiteralPath $uninstallKey) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }

if (Test-Path -LiteralPath $exe) { throw "Executable still present after uninstall" }
if (Test-Path -LiteralPath $uninstallKey) { throw "Apps & features entry still present after uninstall" }
if (Test-Path -LiteralPath $startMenu) { throw "Start menu shortcut still present after uninstall" }
if (Test-Path -LiteralPath $desktop) { throw "Desktop shortcut still present after uninstall" }
if (Get-Process -Name "Arnold DW" -ErrorAction SilentlyContinue) { throw "App still running after uninstall" }
if (Test-Path -LiteralPath $runtimeDir) { throw "Downloaded components still present after uninstall: $runtimeDir" }

Write-Host "Installer smoke test passed."
