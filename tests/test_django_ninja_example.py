def test_django_ninja_example_exposes_docs_and_schema():
    import importlib.util
    import sys
    from pathlib import Path

    from django.test import Client, override_settings

    example_path = Path(__file__).resolve().parents[1] / "examples" / "django_ninja_app.py"
    spec = importlib.util.spec_from_file_location("django_ninja_app_example", example_path)
    assert spec is not None
    assert spec.loader is not None
    example = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = example
    spec.loader.exec_module(example)

    client = Client()

    with override_settings(ROOT_URLCONF=spec.name):
        docs = client.get("/doc.html")
        schema = client.get("/api/openapi.json")

    assert example.urlpatterns
    assert docs.status_code == 200
    assert b'id="root"' in docs.content
    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == "Knife4p Django Ninja Example"
