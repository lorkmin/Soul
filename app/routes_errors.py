from flask import Flask, render_template, request

def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        # чтобы в journalctl было видно, где упало
        app.logger.exception("500 error on %s", request.path)
        return render_template("errors/500.html"), 500
