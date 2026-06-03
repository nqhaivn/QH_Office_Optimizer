# QH Office Optimizer 1.0

Ung dung desktop Windows dung de toi uu anh nhung trong cac tep `.docx`, `.xlsx`, `.pptx` bang ImageMagick.

## Chay ung dung

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python -m qh_office_optimizer
```

## Cai moi moi truong

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## Dong goi EXE

```powershell
.\.venv\Scripts\pyinstaller --noconsole --name "QH Office Optimizer" --paths src src\qh_office_optimizer\__main__.py
```
