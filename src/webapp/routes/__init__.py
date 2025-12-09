from flask import Flask

from webapp.routes.articles import bp as articles_bp
from webapp.routes.digests import bp as digests_bp


def register_blueprints(app: Flask) -> None:
    """Attach all blueprints to the Flask app."""
    app.register_blueprint(articles_bp)
    app.register_blueprint(digests_bp)

