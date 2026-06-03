APP_TITLE = "QH Office Optimizer 1.0"
HELP_TITLE = "Hướng dẫn QH Office Optimizer"

IMAGE_SIZE_LABELS = ["3840px", "2560px", "1920px", "1080px", "720px", "640px"]
DEFAULT_IMAGE_SIZE_LABEL = "1920px"

OUTPUT_OVERWRITE = "Đè tệp gốc"
OUTPUT_FOLDER = "Thư mục khác"
OUTPUT_SUFFIX = "Thêm hậu tố _opt"
OUTPUT_LABELS = [OUTPUT_OVERWRITE, OUTPUT_FOLDER, OUTPUT_SUFFIX]
DEFAULT_OUTPUT_LABEL = OUTPUT_FOLDER

WRN001 = "Không tìm thấy Magick.exe hoặc chương trình đã bị chặn, hãy đọc hướng dẫn để biết thêm chi tiết."
ERR006 = "Không thể khởi chạy magick.exe"

HELP_TEXT = """【 1 】    GIỚI THIỆU:
    Phần mềm hoạt động bằng cách sử dụng Magick để giảm dung lượng nhưng vẫn giữ nguyên chất lượng ảnh đính kèm trong các tệp Word, Excel hoặc Powerpoint, nhờ đó giúp giảm dung lượng tổng thể của tệp tin.

    Magick.exe là bắt buộc phải có để sử dụng phần mềm này, nếu bạn vô tình xóa mất và gặp báo lỗi thiếu magick.exe, chỉ cần tải lại từ: https://github.com/nqhaivn/QH_Office_Optimizer/releases

【 2 】    CÁC TÙY CHỌN:
    "Kích thước ảnh" sẽ giới hạn kích thước cạnh dài nhất của ảnh (theo pixels) không vượt quá mức này. Đối với Powerpoint, nên chọn từ 1920-3840px. Đối với Word, nên chọn từ 720-1920px. Đối với Excel, nên chọn từ 720px trở xuống.

    "Đầu ra" có các lựa chọn gồm:
        - "Đè tệp gốc": Tệp sau khi tối ưu sẽ ghi đè thẳng vào tệp gốc (nên thận trọng)
        - "Thư mục khác": Tệp sau khi tối ưu sẽ được ghi vào một thư mục có cùng tên và cùng thư mục mẹ với tệp gốc.
        - "Thêm hậu tố _opt": Tệp sau khi tối ưu sẽ được ghi vào cùng thư mục mẹ với tệp gốc, tên tệp có thêm hậu tố _opt để dễ phân biệt.

【 3 】    TÁC GIẢ

    Phần mềm QH Office Optimizer 1.0 được viết bởi facebook.com/nqhaivn/, phát hành ngày 03/06/2026.

    Mọi hành vi chỉnh sửa lại mã nguồn mà chưa được sự đồng ý bằng văn bản của tác giả thì đều là trộm cắp.

    Mọi góp ý, báo lỗi, có nhu cầu tùy chỉnh phần mềm theo sở thích của bản thân hoặc muốn đề nghị thiết kế phần mềm khác, vui lòng liên lạc với email: nqhai86@gmail.com

    Trân trọng!"""
