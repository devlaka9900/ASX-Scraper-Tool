# Welcome

This is the **ASX Reg Data** tool (repository name: `ASX-Scraper-Tool`). It scrapes a regulator web page, downloads every PDF, checks each PDF's dates against a cut-off date, creates the updated PDFs, and writes reports (`analysis_report.md`, `updated_page_count.md`, `report.xlsx`).

It ships as a Windows desktop app (PySide6 GUI) packaged into an exe with PyInstaller. A command-line version also exists.

This page takes you from an empty machine to a built exe. Run every command from the **project root** in **PowerShell**.

---

## 1. What you need installed

| Tool | Notes |
|------|-------|
| Git | https://git-scm.com/download/win |
| Python (64-bit) | https://www.python.org/downloads/ - tick **Add python.exe to PATH** during install |
| PowerShell | Built into Windows 10/11 |
| Internet access | Needed to install packages and to reach `www.asx.com.au` when running |

Check them:

```powershell
git --version
python --version
```

---

## 2. Clone the project

```powershell
git clone https://github.com/devlaka9900/ASX-Scraper-Tool.git
cd ASX-Scraper-Tool
```

Branches: `main` is the stable branch. Do your work on your own branch:

```powershell
git checkout main
git pull
git checkout -b Dev-YourName
```

Keep the folder path short (for example `C:\Work\ASX-Scraper-Tool`). Long paths cause Windows "file not found" errors.

---

## 3. First-time setup

Create the virtual environment and install everything (run once):

```powershell
python -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install -r requirements-gui.txt
```

`requirements-gui.txt` installs the runtime packages plus PySide6 (GUI), PyInstaller (build) and PyMuPDF (PDF handling).

If pip is slow or times out:

```powershell
.venv-build\Scripts\python.exe -m pip install --default-timeout 90 --retries 10 -r requirements-gui.txt
```

Command-line tool only (no GUI, no build tools):

```powershell
pip install -r requirements.txt
```

---

## 4. Run the app

| What | Command |
|------|---------|
| Desktop GUI from source | `.venv-build\Scripts\python.exe gui_main.py` |
| Command-line tool (scrape, download, report) | `python main.py` |
| Re-check dates of already downloaded PDFs | `python check_pdf_dates.py` |
| Built exe | `dist\ASX Reg Data\ASX Reg Data.exe` |

If the command-line tool prints an encoding error:

```powershell
$env:PYTHONUTF8 = "1"; python main.py
```

Results are written to `output\<DocumentId>\`.

---

## 5. Run the tests

Run all four before every build. Each one ends with `ALL PASS` and exits with a non-zero code on failure.

```powershell
# pipeline, cancel, history, date checker, notes, job runner (uses a local test server, no internet)
.venv-build\Scripts\python.exe tools\e2e_local.py

# headless UI tests
.venv-build\Scripts\python.exe tools\ui_interaction_test.py

# documentation structure and version/changelog rule
.venv-build\Scripts\python.exe tools\docs_check.py

# smoke test: imports, round trips, renders every page in both themes
.venv-build\Scripts\python.exe gui_main.py --selftest
```

---

## 6. Build the exe

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

The script does the following, in order, and stops at the first failure:

1. Reads the version from `core\version.py`.
2. Installs the pinned packages into `.venv-build`.
3. Checks the docs.
4. Builds with PyInstaller into `build\stage`.
5. Runs the self-test on the built exe.
6. Launches the exe for 8 seconds and checks it closes cleanly.
7. Creates `dist\ASX_Reg_Data_v<version>.zip`.
8. Refreshes the runnable folder `dist\ASX Reg Data\` (only if the exe is not running).

Variants:

| Purpose | Command |
|---------|---------|
| Skip the 8 second launch test | `powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipSmoke` |
| Publish the last build into `dist` (after closing the app) | `powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -PublishOnly` |

Outputs:

| Path | What it is |
|------|------------|
| `dist\ASX_Reg_Data_v<version>.zip` | The file you hand to other people |
| `dist\ASX Reg Data\` | Runnable folder |
| `build\stage\` | The verified build |

Check a built exe by hand:

```powershell
& "dist\ASX Reg Data\ASX Reg Data.exe" --selftest
(Get-Item "dist\ASX Reg Data\ASX Reg Data.exe").VersionInfo.FileVersion
```

Exit code `0` from the self-test means the build is healthy.

---

## 7. Release a new version

Version format is `MAJOR.FEATURE.FIX`. Example: `1.2.0` becomes `1.2.1` for a bug fix, `1.3.0` for a new feature, `2.0.0` for a major release.

1. Change `APP_VERSION` in `core\version.py`.
2. In `docs\index.html`, add an `<h3>X.Y.Z</h3>` entry to the **Changelog** tab and update the version in the header and footer text.
3. Run the tests (section 5).
4. Run the build (section 6).
5. Commit and tag (section 8).

The docs check fails the build if the version is not `N.N.N`, is missing from the docs, or has no changelog entry.

---

## 8. Everyday Git

```powershell
git status --short
git add -A
git commit -m "v1.2.1: short description of the change"
git push -u origin Dev-YourName
git pull
git tag v1.2.1
```

`dist/`, `build/`, `downloads/` and `output/` are git-ignored. If `.venv-build/` shows up in `git status`, add it to `.gitignore`.

---

## 9. Give the exe to someone else

1. Send `dist\ASX_Reg_Data_v<version>.zip`. Optional checksum: `Get-FileHash dist\ASX_Reg_Data_v<version>.zip`
2. They unzip it to a short, writable folder such as `C:\Tools\ASX Reg Data\` (not `Program Files`).
3. They keep the whole folder together; the exe needs the `_internal` folder next to it.
4. They run `ASX Reg Data.exe`. Python is not needed. Windows 10 1809 or newer / Windows 11 (64-bit) and internet access to `www.asx.com.au` are required.
5. The exe is unsigned, so Windows SmartScreen or antivirus may warn. Right-click the zip, choose **Properties**, tick **Unblock**, then unzip. On the SmartScreen prompt choose **More info**, then **Run anyway**. For a permanent fix, ask IT to whitelist the exe or sign it with a code-signing certificate.

---

## 10. Project layout

| Path | Purpose |
|------|---------|
| `gui_main.py` | GUI entry point (`--selftest` mode) |
| `main.py`, `check_pdf_dates.py` | Command-line tools |
| `core\` | Pipeline, summary, date check, notes, paths, version (no GUI code) |
| `gui\` | PySide6 app: pages, widgets, theme, workers, main window |
| `scraper\`, `analyzer\`, `reporter\`, `utils\` | Scraping, PDF date analysis, report writing, helpers |
| `packaging\` | `build.ps1`, PyInstaller spec, version resource, icon |
| `tools\` | Test and utility scripts |
| `docs\index.html` | Offline documentation (open with `start docs\index.html`) |

Runtime data for each Windows user is stored in `%LOCALAPPDATA%\ASX Reg Data\`: `logs\asx_checker.log`, `logs\crash.log` and `notes.json`.

---

## 11. Troubleshooting

| Problem | Fix |
|---------|-----|
| Build fails with "Access is denied" inside `dist\...\_internal` | An old exe is still running from that folder. Close it and build again. |
| Build says publishing was **SKIPPED** | The app is running from `dist`. Close it, then run `packaging\build.ps1 -PublishOnly`. The zip is already complete. |
| pip downloads time out | Use `--default-timeout 90 --retries 10` (section 3). |
| `UnicodeEncodeError` in the command-line tool | Run `$env:PYTHONUTF8 = "1"` first. |
| Many "No such file or directory" errors while downloading | Windows 260-character path limit. Use a shorter output folder or DocumentId. |
| App window never appears | Read `%LOCALAPPDATA%\ASX Reg Data\logs\crash.log`. |
| `running scripts is disabled` | Always start the build with `powershell -ExecutionPolicy Bypass -File ...` as shown above. |
| Notes file unreadable | Look for `notes.corrupt-*.json` or `notes.json.bak` in `%LOCALAPPDATA%\ASX Reg Data\`. |
| Text shows as empty boxes in test screenshots | Set `$env:QT_QPA_PLATFORM = "windows"` before running the self-test. |
