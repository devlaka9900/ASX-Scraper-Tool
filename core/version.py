"""Single source of truth for the app name and version.

Versioning rule  MAJOR.FEATURE.FIX  (e.g. 1.2.0):
  * MAJOR   — a major release (first number): 1.x.x -> 2.0.0
  * FEATURE — a feature release (second number): new capability, resets FIX: 1.1.3 -> 1.2.0
  * FIX     — a bug-fix release (third number): no new features: 1.2.0 -> 1.2.1
Bump it here, add a Changelog entry in docs/index.html (tools/docs_check.py enforces both)
and run packaging/build.ps1.
"""

APP_NAME = "ASX PDF Checker"
APP_VERSION = "1.2.0"
