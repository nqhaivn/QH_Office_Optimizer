def format_size(size_bytes: int) -> str:
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024):.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def parse_image_size_label(label: str) -> int:
    text = label.strip().lower()
    if not text.endswith("px"):
        raise ValueError(f"Invalid image size label: {label}")
    return int(text[:-2])
