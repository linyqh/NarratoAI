"""Application configuration - root APIRouter.

Defines all FastAPI application endpoints.

Resources:
    1. https://fastapi.tiangolo.com/tutorial/bigger-applications

"""

from fastapi import APIRouter

from app.controllers.v1 import llm, video
from app.controllers.v2 import script

root_api_router = APIRouter()
# v1
root_api_router.include_router(video.router)
root_api_router.include_router(llm.router)

# v2
root_api_router.include_router(script.router)
