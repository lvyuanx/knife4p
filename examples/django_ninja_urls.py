from django.urls import include, path
from ninja import NinjaAPI

from knife4p import Knife4pConfig, OpenAPIGroup, django_urls

api = NinjaAPI()


@api.get("/ping")
def ping(request):
    return {"pong": True}


urlpatterns = [
    path("api/", api.urls),
    path("", include(django_urls(Knife4pConfig(groups=[OpenAPIGroup(name="default", openapi_url="/api/openapi.json")])))),
]
