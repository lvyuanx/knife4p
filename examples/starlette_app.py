from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from knife4p import Knife4pConfig, OpenAPIGroup, mount_fastapi


async def health(request):
    return JSONResponse({"ok": True})


app = Starlette(routes=[Route("/health", health)])
mount_fastapi(app, Knife4pConfig(groups=[OpenAPIGroup(name="default", openapi_url="/openapi.json")]))
