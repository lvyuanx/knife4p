import json
import shutil
import subprocess
from pathlib import Path

import pytest


ASSET = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "knife4p"
    / "assets"
    / "webjars"
    / "knife4j-ui-react"
    / "assets"
    / "index.js"
)


def generate_markdown_from_asset(operation, doc):
    if shutil.which("node") is None:
        pytest.skip("node is required to execute the bundled frontend asset")

    script = r"""
const fs = require("fs");
const vm = require("vm");
const assetPath = process.argv[1];
const operation = JSON.parse(process.argv[2]);
const doc = JSON.parse(process.argv[3]);
const source = fs.readFileSync(assetPath, "utf8");
const start = source.indexOf("var IR={},Fu={},L8;function kw()");
const end = source.indexOf("var j8;", start);
if (start < 0 || end < 0) {
  throw new Error("Unable to locate markdown module in bundled asset");
}
const stubs = `
function fDe(){return {}}
function pDe(){return {}}
function UX(){return {buildMediaTypeExampleValue:function(){}}}
`;
const context = { Object, Array, Set, String, console, operation, doc };
vm.runInNewContext(stubs + source.slice(start, end) + `
this.markdown = hDe().generateApiMarkdown({
  method: "GET",
  path: "/projects",
  operation,
  docContext: doc
});
`, context);
process.stdout.write(context.markdown);
"""
    result = subprocess.run(
        ["node", "-e", script, str(ASSET), json.dumps(operation), json.dumps(doc)],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_copied_markdown_expands_anyof_ref_response_schema():
    operation = {
        "summary": "Save choreography project",
        "responses": {
            "200": {
                "description": "OK",
                "content": {
                    "application/json": {
                        "schema": {
                            "anyOf": [
                                {
                                    "$ref": "#/components/schemas/SuccessResponse_ChoreographyProjectSaveOut_"
                                },
                                {"$ref": "#/components/schemas/ErrorResponse_dict_"},
                            ],
                            "title": "Response",
                        }
                    }
                },
            }
        },
    }
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "knife4p test", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "SuccessResponse_ChoreographyProjectSaveOut_": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "Status code",
                        },
                        "msg": {"type": "string", "description": "Message"},
                        "data": {
                            "anyOf": [
                                {
                                    "$ref": "#/components/schemas/ChoreographyProjectSaveOut"
                                },
                                {"type": "null"},
                            ],
                            "description": "Payload",
                        },
                    },
                },
                "ErrorResponse_dict_": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "msg": {"type": "string"},
                    },
                },
                "ChoreographyProjectSaveOut": {
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "编排作品 ID",
                        },
                        "name": {
                            "type": "string",
                            "description": "编排作品名称",
                        },
                    },
                    "required": ["project_id", "name"],
                },
            }
        },
    }

    markdown = generate_markdown_from_asset(operation, doc)

    assert "| `code` | string | No | Status code |" in markdown
    assert "| `msg` | string | No | Message |" in markdown
    assert "| `data` | object | No | Payload |" in markdown
    assert "| `data.project_id` | integer | Yes | 编排作品 ID |" in markdown
    assert "| `data.name` | string | Yes | 编排作品名称 |" in markdown
    assert "| 200 | OK | object |" not in markdown


def test_copied_markdown_omits_request_body_section_when_operation_has_no_body():
    operation = {
        "summary": "Validate deployment token",
        "parameters": [
            {
                "in": "header",
                "name": "authorization",
                "schema": {
                    "description": "模型部署工具 Bearer token",
                    "type": "string",
                },
                "required": True,
                "description": "模型部署工具 Bearer token",
            }
        ],
        "responses": {"200": {"description": "OK"}},
    }
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "knife4p test", "version": "1.0.0"},
        "paths": {},
    }

    markdown = generate_markdown_from_asset(operation, doc)

    assert "## Request Body" not in markdown
    assert "*No request body.*" not in markdown


def test_copied_markdown_keeps_request_body_section_when_operation_has_body():
    operation = {
        "summary": "Create project",
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Project name",
                            }
                        },
                        "required": ["name"],
                    }
                }
            }
        },
        "responses": {"200": {"description": "OK"}},
    }
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "knife4p test", "version": "1.0.0"},
        "paths": {},
    }

    markdown = generate_markdown_from_asset(operation, doc)

    assert "## Request Body" in markdown
    assert "| `name` | string | Yes | Project name |" in markdown
