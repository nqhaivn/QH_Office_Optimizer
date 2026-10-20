# QH Office Optimizer 1.0

Ứng dụng desktop Windows dùng để tối ưu ảnh nhúng trong các tệp `.docx`, `.xlsx`, `.pptx` bằng ImageMagick.

## Chạy ứng dụng

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python -m qh_office_optimizer
```

## Cài mới môi trường

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## Đóng gói EXE

```powershell
.\.venv\Scripts\pyinstaller --noconfirm --clean --onedir --noconsole --name QH_Office_Optimizer --icon src\qh_office_optimizer\icon.ico --paths src --add-data "src\qh_office_optimizer\icon.ico;qh_office_optimizer" --contents-directory resource --distpath releases --workpath build\pyinstaller src\qh_office_optimizer\__main__.py
```
