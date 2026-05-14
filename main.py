from fastapi import FastAPI

from api.routes import github, health, jira, sandbox, test_routes
from services.cloudinary_service import configure_cloudinary


def create_app() -> FastAPI:
    app = FastAPI(title="Automation Testing API")

    configure_cloudinary()

    app.include_router(health.router)
    app.include_router(jira.router)
    app.include_router(github.router)
    app.include_router(sandbox.router)
    app.include_router(test_routes.router)

    return app


app = create_app()
