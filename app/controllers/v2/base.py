from fastapi import APIRouter, Depends


def v2_router(dependencies=None):
    router = APIRouter()
    router.tags = ["V2"]
    router.prefix = "/api/v2"
    # 将认证依赖项应用于所有路由
    if dependencies:
        router.dependencies = dependencies
    return router
