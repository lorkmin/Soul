# Refactor: разнесённый app.py

Эта папка — готовая нарезка вашего монолитного `app.py` на модули без смены URL и endpoint-имён,
чтобы `url_for("admin_enrolls")` и остальные ссылки в шаблонах продолжили работать.

## Что внутри

- `app/__init__.py` — `create_app()` (factory), регистрация фильтров/глобалов/роутов
- `app/config.py` — конфиг из env + пути
- `app/db.py` — SQLite + init_db (таблицы/миграции)
- `app/utils.py` — upload/helpers
- `app/telegram.py` — отправка в телеграм (как было)
- `app/auth.py` — декораторы login_required / teacher_login_required
- `app/routes_*.py` — роуты по зонам ответственности

- `wsgi.py` — точка входа для gunicorn
- `run.py` — запуск в debug

## Как внедрить в проект

1) Скопируйте содержимое этой папки в корень проекта рядом с `templates/`, `static/`, `soul.db`.
   (То есть `app/`, `wsgi.py`, `run.py`).

2) В вашем systemd unit для gunicorn замените `app:app` на `wsgi:app`, например:
   `ExecStart=/opt/Soul/venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 wsgi:app`

3) Перезапустите сервис.

## Примечание

- Миграции в `init_db` добавляют `enrolls.admin_note` и `enrolls.is_bot`, если их ещё нет.
- `split_tags` добавлен в `jinja_env.globals`, чтобы удобно рендерить теги курса.
