from flask import Flask

def format_paragraphs(text: str) -> str:
    """Convert empty-line separated text to HTML paragraphs."""
    if not text:
        return ""
    parts = [p.strip() for p in text.replace("\r", "").split("\n\n")]
    return "".join(f"<p>{p}</p>" for p in parts if p)

def register_filters(app: Flask) -> None:
    app.jinja_env.filters["paragraphs"] = format_paragraphs
