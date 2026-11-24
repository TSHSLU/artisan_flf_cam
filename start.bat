cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -e ".[dev]"
)
start "" .venv\Scripts\pythonw.exe -m artisancam