from functools import wraps
from flask import session, redirect, url_for, request

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return wrapper

def teacher_login_required(f):
    """Allow access if admin is logged in OR teacher key session is present."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("admin_logged_in") or session.get("teacher_logged_in"):
            return f(*args, **kwargs)
        return redirect(url_for("teacher_login", next=request.path))
    return wrapper

def student_login_required(f):
    """
    Доступ разрешён, если в session есть student_id.
    Если нет — отправляем на /student (student_dashboard),
    потому что отдельного student_login у нас нет.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("student_id"):
            return redirect(url_for("student_dashboard", next=request.path))
        return f(*args, **kwargs)
    return wrapper


