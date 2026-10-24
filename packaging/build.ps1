<#
  Builds the ASX Reg Data GUI: venv -> PyInstaller (onedir, windowed) in a STAGING folder
  -> self-test gate -> launch smoke test -> zip -> publish into dist\ (only when safe).

    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipSmoke
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -PublishOnly   # re-publish the last staged build

  The ready-to-run folder dist\ASX Reg Data may be in use (someone runs the exe from it, and
  their runs land in dist\ASX Reg Data\output). So the build never touches it until the new build
  has passed every gate, and then only if the exe is not running; the user's output\ is carried over.
  The zip dist\ASX_Reg_Data_v<version>.zip is always produced; older zips are left alone.
#>
param(
    [string]$Version = "",
    [switch]$SkipSmoke,
    [switch]$PublishOnly
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Version) {
    $Version = (Select-String -Path "core\version.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
}
$name = "ASX Reg Data"
if ($Version -notmatch '^\d+(\.\d+){0,3}$') { throw "-Version must be numeric like 1.2.3 or 1.2.3.4 (got '$Version')" }
Write-Host "== $name v$Version ==" -ForegroundColor Cyan

$stageRoot = Join-Path $root "build\stage"
$stageApp  = Join-Path $stageRoot $name
$distApp   = Join-Path $root "dist\$name"
$zip       = Join-Path $root "dist\ASX_Reg_Data_v$Version.zip"

function Test-AppRunning([string]$folder) {
    # any process started from a file inside $folder
    $prefix = (Join-Path $folder "")
    return [bool](Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })
}

function Publish-ToDist {
    # Replace dist\<app> with the staged build, carrying the user's output\ over. Never done while the exe runs.
    if (-not (Test-Path $stageApp)) { throw "nothing staged at $stageApp - run a full build first" }
    if ((Test-Path $distApp) -and (Test-AppRunning $distApp)) {
        Write-Host "SKIPPED publishing to dist\$name : the app is running from there." -ForegroundColor Yellow
        Write-Host "   Close it and run:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -PublishOnly" -ForegroundColor Yellow
        Write-Host "   (the zip $zip is complete and can be unzipped anywhere meanwhile)" -ForegroundColor Yellow
        return
    }
    $userOutput = Join-Path $distApp "output"
    $aside = $null
    try {
        if ((Test-Path $userOutput) -and (Get-ChildItem $userOutput -Force | Select-Object -First 1)) {
            $aside = Join-Path $env:TEMP ("asx_dist_output_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
            Move-Item -LiteralPath $userOutput -Destination $aside
            Write-Host "Preserved dist output -> $aside" -ForegroundColor Yellow
        }
        if (Test-Path $distApp) { Remove-Item $distApp -Recurse -Force }
        New-Item -ItemType Directory -Force (Split-Path $distApp) | Out-Null
        Copy-Item -Path $stageApp -Destination $distApp -Recurse -Force
        Write-Host "Published -> $distApp" -ForegroundColor Green
    }
    finally {
        if ($aside -and (Test-Path $aside)) {
            New-Item -ItemType Directory -Force $distApp | Out-Null
            if (Test-Path $userOutput) { Remove-Item $userOutput -Recurse -Force }   # empty artifact only
            Move-Item -LiteralPath $aside -Destination $userOutput
            Write-Host "Restored dist output -> $userOutput" -ForegroundColor Yellow
        }
    }
}

if ($PublishOnly) { Publish-ToDist; return }

# 1) clean venv with pinned deps (keeps the global Python's unrelated packages out of the bundle)
$venv = Join-Path $root ".venv-build"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) { python -m venv $venv }
& $py -m pip install --disable-pip-version-check --default-timeout 90 --retries 10 -q -r requirements-gui.txt
if ($LASTEXITCODE) { throw "pip install failed" }

# 1b) documentation must be structurally valid (and mention this version) before we ship it
& $py tools\docs_check.py
if ($LASTEXITCODE) { throw "docs check failed" }

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

# 3) build into the staging folder (dist\ is not touched)
if (Test-AppRunning $stageApp) { throw "the staged exe is running; close it and retry" }
Remove-Item (Join-Path $root "build") -Recurse -Force -ErrorAction SilentlyContinue
& $py -m PyInstaller packaging\asx_pdf_checker.spec --noconfirm --clean --distpath $stageRoot --workpath (Join-Path $root "build\work")
if ($LASTEXITCODE) { throw "PyInstaller failed" }
$exe = Join-Path $stageApp "$name.exe"
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

# 6) docs next to the exe (opens in any browser, works offline), then zip + size report.
#    The self-test / smoke launch create an empty output\ in the staged folder; don't ship it.
$leftover = Join-Path $stageApp "output"
if ((Test-Path $leftover) -and -not (Get-ChildItem $leftover -Force)) { Remove-Item $leftover -Force }
Copy-Item -Path (Join-Path $root "docs") -Destination (Join-Path $stageApp "docs") -Recurse -Force
New-Item -ItemType Directory -Force (Join-Path $root "dist") | Out-Null
Remove-Item $zip -ErrorAction SilentlyContinue
tar.exe -a -c -f $zip -C $stageRoot $name
if ($LASTEXITCODE) { throw "zip failed" }
$bytes = (Get-ChildItem $stageApp -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("folder: {0:N0} MB   zip: {1:N0} MB" -f ($bytes / 1MB), ((Get-Item $zip).Length / 1MB)) -ForegroundColor Cyan
Get-ChildItem $stageApp -Recurse -File | Sort-Object Length -Descending | Select-Object -First 12 |
    ForEach-Object { "{0,8:N1} MB  {1}" -f ($_.Length / 1MB), $_.FullName.Substring($root.Length + 1) }

# 7) refresh dist\<app> from the verified build (skipped if the app is running there)
Publish-ToDist
Write-Host "Output: $zip" -ForegroundColor Green
