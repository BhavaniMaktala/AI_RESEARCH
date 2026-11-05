"""Blueprint registration."""
from __future__ import annotations

from api.routes import feedback, graph, health, insights, library, papers, search

BLUEPRINTS = (health.bp, search.bp, papers.bp, graph.bp, library.bp, feedback.bp, insights.bp)


def register_routes(app) -> None:
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
