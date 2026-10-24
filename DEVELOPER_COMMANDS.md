# Developer commands — ASX PDF Checker

Run everything from the project root in **PowerShell**. Paths use `.venv-build\Scripts\python.exe`
(the pinned build/test virtual environment); `python` alone means your global Python.

---

## 1. First-time setup

```powershell
python -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install -r requirements-gui.txt
```

`requirements-gui.txt` = runtime deps + `PySide6-Essentials==6.12.0` + `pyinstaller==6.20.0` + `PyMuPDF==1.28.0`.
(CLI only, no GUI/build tools: `pip install -r requirements.txt`.)

If pip stalls on a flaky network, retry with longer timeouts:

```powershell
.venv-build\Scripts\python.exe -m pip install --default-timeout 90 --retries 10 -r requirements-gui.txt
```

---

## 2. Run the app

| What | Command |
|------|---------|
| Desktop GUI from source | `.venv-build\Scripts\python.exe gui_main.py` |
| Command-line tool (scrape → download → report) | `python main.py` |
| Re-check dates of already-downloaded PDFs (CLI) | `python check_pdf_dates.py` |
| Packaged exe | `dist\ASX PDF Checker\ASX PDF Checker.exe` |

Set `PYTHONUTF8=1` if the CLI prints encoding errors on a legacy console:

```powershell
$env:PYTHONUTF8 = "1"; python main.py
```

---

## 3. Tests (run before every build)

```powershell
# core pipeline, cancel, history, date checker, Notes store, JobRunner (local HTTP server, no internet)
.venv-build\Scripts\python.exe tools\e2e_local.py

# headless UI tests: filters, forms, Notes CRUD, Agent, watermark, navigation guards
.venv-build\Scripts\python.exe tools\ui_interaction_test.py

# docs structure + version/changelog rule
.venv-build\Scripts\python.exe tools\docs_check.py

# headless smoke test (imports, round trips, renders every page in both themes)
.venv-build\Scripts\python.exe gui_main.py --selftest
```

Each prints `PASS` / `FAIL` lines and ends with `ALL PASS`; the exit code is non-zero on failure.

Useful self-test switches (environment variables):

```powershell
$env:ASX_SELFTEST_OUT  = "C:\Temp\shots"      # keep the screenshots + selftest.log here
$env:ASX_SELFTEST_SIZE = "1100x720"           # window size to render (default 1280x820)
$env:QT_QPA_PLATFORM   = "windows"            # real fonts/rendering instead of 'offscreen'
$env:ASX_SELFTEST_URL  = "<ASX page URL>"     # also scrape that page (proves TLS + scraper)
```

Live comparison of the CLI against the GUI pipeline (needs internet, writes to a temp folder):

```powershell
.venv-build\Scripts\python.exe tools\parity_check.py demo-id "<ASX page URL>" 2024-01-01 "$env:TEMP\parity"
```

---

## 4. Build the exe

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

What it does: reads the version from `core\version.py` → installs pinned deps in `.venv-build` →
docs check → PyInstaller into `build\stage` → **self-test gate** → **launch/clean-exit gate** →
zip to `dist\ASX_PDF_Checker_v<version>.zip` → refresh `dist\ASX PDF Checker` (only if the exe is not running;
a user's `output\` folder there is preserved).

| Variant | Command |
|---------|---------|
| Skip the 8 s launch test | `powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipSmoke` |
| Publish the last staged build into `dist` (after closing the app) | `powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -PublishOnly` |

Plain PyInstaller (no gates, no zip, no docs — not for releases):

```powershell
.venv-build\Scripts\python.exe -m PyInstaller packaging\asx_pdf_checker.spec --noconfirm --clean
```

Outputs: `dist\ASX_PDF_Checker_v<version>.zip` (hand this to other devs), `dist\ASX PDF Checker\` (runnable folder),
`build\stage\` (the verified build).

Check a built exe by hand:

```powershell
& "dist\ASX PDF Checker\ASX PDF Checker.exe" --selftest      # exit code 0 = healthy
(Get-Item "dist\ASX PDF Checker\ASX PDF Checker.exe").VersionInfo.FileVersion
```

Regenerate the app icon (only if you change the logo): `.venv-build\Scripts\python.exe tools\make_icon.py`

---

## 5. Releasing a new version

Versioning rule **`MAJOR.FEATURE.FIX`**: `1.2.0` → bug fix `1.2.1`, new feature `1.3.0`, major release `2.0.0`.

1. Edit `APP_VERSION` in `core\version.py`.
2. In `docs\index.html`: add a `<h3>X.Y.Z</h3>` entry to the **Changelog** tab and update the version in the header/footer text.
3. Run the tests (section 3), then `packaging\build.ps1` (section 4).
4. Give people the zip (see section 8). Commit when ready (section 7).

`tools\docs_check.py` (also run by the build) fails if the version is not `N.N.N`, is missing from the docs,
or has no Changelog entry.

---

## 6. Where things live

| Path | Purpose |
|------|---------|
| `gui_main.py` | GUI entry point (`--selftest` mode) |
| `main.py`, `check_pdf_dates.py` | original CLI tools |
| `core\` | Qt-free logic: `pipeline.py`, `summary.py`, `datecheck.py`, `notes.py`, `paths.py`, `version.py` |
| `gui\` | PySide6 app: `pages\`, `widgets\`, `theme.py`, `workers.py`, `main_window.py` |
| `scraper\`, `analyzer\`, `reporter\`, `utils\` | shared scrape / PDF-date / report code |
| `packaging\` | `build.ps1`, `asx_pdf_checker.spec`, version resource, icon |
| `tools\` | dev-only test and utility scripts |
| `docs\index.html` | offline documentation (SRS, tech stack, architecture, guides) |

Runtime data (per Windows user): `%LOCALAPPDATA%\ASX PDF Checker\` → `logs\asx_checker.log`, `logs\crash.log`, `notes.json`.
Run output: `output\<DocumentId>\` next to the exe (or the folder chosen on the New run page).

Open the docs: `start docs\index.html`

---

## 7. Git

```powershell
git status --short
git add -A
git commit -m "v1.2.0: DocumentId, Startpoint, Notes, Agent placeholder"
git tag v1.2.0
```

`dist/`, `build/` and `downloads/` are git-ignored; `.venv-build/` is **not** — add it to `.gitignore` if it shows up in `git status`.

---

## 8. Handing the exe to other devs (no repo needed)

1. Send `dist\ASX_PDF_Checker_v<version>.zip` (optional checksum: `Get-FileHash dist\ASX_PDF_Checker_v1.2.0.zip`).
2. They unzip to a **short, writable** path (e.g. `C:\Tools\ASX PDF Checker\`), not `Program Files`.
3. Run `ASX PDF Checker.exe`. The exe is unsigned: on the SmartScreen prompt choose *More info → Run anyway*.
4. Needs Windows 10 1809+/11 (64-bit) and internet access to `www.asx.com.au`. No Python required.
5. Keep the whole unzipped folder together (the exe needs `_internal\`).

---

## 9. Troubleshooting cheat sheet

| Symptom | Fix |
|---------|-----|
| Build fails with *Access is denied* in `dist\…\_internal` | An old exe is running from that folder. Close it; the current `build.ps1` builds in `build\stage` and publishes only when it is closed. |
| `build.ps1` says publishing was **SKIPPED** | The app is running from `dist`. Close it, then `build.ps1 -PublishOnly`. The zip is already complete. |
| Text shows as empty boxes in test screenshots | Offscreen Qt has no fonts: set `QT_QPA_PLATFORM=windows` (or leave `QT_QPA_FONTDIR` as the self-test sets it). |
| Many "No such file or directory" download errors | Windows 260-character path limit: use a shorter output folder or DocumentId. |
| pip downloads time out / hang | Retry with `--default-timeout 90 --retries 10` (section 1). |
| CLI prints `UnicodeEncodeError` | `$env:PYTHONUTF8 = "1"` before running. |
| GUI crashed with no window | Read `%LOCALAPPDATA%\ASX PDF Checker\logs\crash.log`. |
| Notes file unreadable | Look for `notes.corrupt-*.json` / `notes.json.bak` in `%LOCALAPPDATA%\ASX PDF Checker\`. |
| Tests touch my real notes? | They don't: tests and the self-test use temp note files. |
