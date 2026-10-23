<#
  Builds the ASX PDF Checker GUI: venv -> PyInstaller (onedir, windowed) -> self-test gate
  -> launch smoke test -> zip.

    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipSmoke
#>
param(
    [string]$Version = "",
    [switch]$SkipSmoke
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Version) {
    $Version = (Select-String -Path "core\version.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
}
$name = "ASX PDF Checker"
if ($Version -notmatch '^\d+(\.\d+){0,3}$') { throw "-Version must be numeric like 1.2.3 or 1.2.3.4 (got '$Version')" }
Write-Host "== $name v$Version ==" -ForegroundColor Cyan

# 1) clean venv with pinned deps (keeps the global Python's unrelated packages out of the bundle)
$venv = Join-Path $root ".venv-build"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) { python -m venv $venv }
& $py -m pip install --disable-pip-version-check --default-timeout 90 --retries 10 -q -r requirements-gui.txt
if ($LASTEXITCODE) { throw "pip install failed" }

# 2) version resource + icon
$parts = ($Version -split '\.') + @('0','0','0','0') | Select-Object -First 4
$tuple = $parts -join ', '
$dotted = $parts -join '.'
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($tuple), prodvers=($tuple), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'CUBE'),
      StringStruct('FileDescription', '$name'),
      StringStruct('FileVersion', '$dotted'),
      StringStruct('InternalName', '$name'),
      StringStruct('OriginalFilename', '$name.exe'),
      StringStruct('ProductName', '$name'),
      StringStruct('ProductVersion', '$dotted')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Path "packaging\version_info.txt" -Encoding utf8
if (-not (Test-Path "packaging\app.ico")) { & $py tools\make_icon.py }

# 3) build
Remove-Item build, dist -Recurse -Force -ErrorAction SilentlyContinue
& $py -m PyInstaller packaging\asx_pdf_checker.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE) { throw "PyInstaller failed" }
$exe = Join-Path $root "dist\$name\$name.exe"
if (-not (Test-Path $exe)) { throw "exe not found: $exe" }

# 4) self-test gate (windowed exe: results go to selftest.log)
$out = Join-Path $env:TEMP "asx_selftest_build"
Remove-Item $out -Recurse -Force -ErrorAction SilentlyContinue
$env:ASX_SELFTEST_OUT = $out
$p = Start-Process -FilePath $exe -ArgumentList "--selftest" -Wait -PassThru
Remove-Item Env:\ASX_SELFTEST_OUT
if (Test-Path "$out\selftest.log") { Get-Content "$out\selftest.log" }
if ($p.ExitCode -ne 0) { throw "self-test failed (exit $($p.ExitCode))" }
Write-Host "self-test OK" -ForegroundColor Green

# 5) launch smoke test: window appears and the process stays alive
if (-not $SkipSmoke) {
    $crash = Join-Path $env:LOCALAPPDATA "$name\logs\crash.log"
    $before = if (Test-Path $crash) { (Get-Item $crash).Length } else { 0 }
    $proc = Start-Process -FilePath $exe -PassThru
    Start-Sleep -Seconds 8
    $proc.Refresh()
    $alive = -not $proc.HasExited
    $window = $alive -and ($proc.MainWindowHandle -ne 0)
    $closedClean = $false
    if ($alive) {
        # close the window like a user would; a clean shutdown must exit with code 0
        [void]$proc.CloseMainWindow()
        if ($proc.WaitForExit(10000)) { $closedClean = ($proc.ExitCode -eq 0) } else { Stop-Process -Id $proc.Id -Force }
    }
    $after = if (Test-Path $crash) { (Get-Item $crash).Length } else { 0 }
    if (-not $alive) { throw "launch smoke test: process exited early (code $($proc.ExitCode))" }
    if (-not $window) { throw "launch smoke test: no main window" }
    if (-not $closedClean) { throw "launch smoke test: did not exit cleanly after closing the window" }
    if ($after -gt $before) { throw "launch smoke test: crash.log grew" }
    Write-Host "launch smoke test OK" -ForegroundColor Green
}

# 6) zip + size report (the smoke launch creates an empty output\ next to the exe; don't ship it)
$leftover = Join-Path $root "dist\$name\output"
if ((Test-Path $leftover) -and -not (Get-ChildItem $leftover -Force)) { Remove-Item $leftover -Force }
$zip = Join-Path $root "dist\ASX_PDF_Checker_v$Version.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
tar.exe -a -c -f $zip -C dist $name
$bytes = (Get-ChildItem "dist\$name" -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("folder: {0:N0} MB   zip: {1:N0} MB" -f ($bytes / 1MB), ((Get-Item $zip).Length / 1MB)) -ForegroundColor Cyan
Get-ChildItem "dist\$name" -Recurse -File | Sort-Object Length -Descending | Select-Object -First 12 |
    ForEach-Object { "{0,8:N1} MB  {1}" -f ($_.Length / 1MB), $_.FullName.Substring($root.Length + 1) }
Write-Host "Output: $zip" -ForegroundColor Green
