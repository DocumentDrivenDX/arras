# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The OpenAPI 3.1 description of the operator surface (CONTRACT-009), served at `/openapi.json`."""

from __future__ import annotations

from typing import Any

from arras.versions import CONTRACT_VERSIONS

# -- the published description -------------------------------------------------------------------


def openapi_document(title: str = "Arras") -> dict[str, Any]:
    """OpenAPI 3.1 for the endpoints of CONTRACT-009. Per-module entity types are not here: a client
    reads those by introspecting the console's GraphQL schema."""
    obj: dict[str, Any] = {"type": "object"}
    err = {"$ref": "#/components/schemas/Error"}
    refused = {"oneOf": [err, {"$ref": "#/components/schemas/NotOperator"}]}

    def schema_of(code: str) -> dict[str, Any]:
        """A non-operator is refused 403 in its own shape (CONTRACT-010), on every endpoint that
        runs as the viewer."""
        return refused if code == "403" else err

    def post(summary: str, req: str, res: str, never: tuple[str, ...] = ()) -> dict[str, Any]:
        """`never`: the codes this endpoint cannot answer (validate reports a false precondition
        in its 200; a read meets no conflict and no precondition)."""
        responses = {
            "200": {
                "description": res,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{res}"}}
                },
            },
            **{
                c: {"description": d, "content": {"application/json": {"schema": schema_of(c)}}}
                for c, d in _STATUS_TEXT.items()
                if c not in never
            },
        }
        return {
            "post": {
                "summary": summary,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": f"#/components/schemas/{req}"}}
                    },
                },
                "responses": responses,
            }
        }

    action_path = {
        "parameters": [
            {"name": "module", "in": "path", "required": True, "schema": {"type": "string"}},
            {"name": "action", "in": "path", "required": True, "schema": {"type": "string"}},
        ]
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"{title} operator surface",
            "version": str(CONTRACT_VERSIONS["operate"]),
        },
        "paths": {
            "/version": {
                "get": {
                    "summary": "Contract versions",
                    "responses": {
                        "200": {
                            "description": "Versions",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Version"}
                                }
                            },
                        }
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "This document",
                    "responses": {
                        "200": {
                            "description": "OpenAPI 3.1",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        **obj,
                                        "properties": {
                                            k: obj if k != "openapi" else {"type": "string"}
                                            for k in ("openapi", "info", "paths", "components")
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/viewer": {
                "get": {
                    "summary": "The viewer's modes: admin is offered to an operator only",
                    "responses": {
                        "200": {
                            "description": "Viewer",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Viewer"}
                                }
                            },
                        },
                        **{
                            c: {"description": d, "content": {"application/json": {"schema": err}}}
                            for c, d in _STATUS_TEXT.items()
                            if c in ("401", "405")
                        },
                    },
                }
            },
            "/explorer/schema-catalog.json": {
                "get": {
                    "summary": "The viewer's catalog for UMF's schema explorer: each module they "
                    "may read, with its registered UMF document verbatim",
                    "responses": {
                        "200": {
                            "description": "SchemaCatalog",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/SchemaCatalog"}
                                }
                            },
                        },
                        **{
                            c: {
                                "description": d,
                                "content": {"application/json": {"schema": schema_of(c)}},
                            }
                            for c, d in _STATUS_TEXT.items()
                            if c in ("401", "403", "405", "429", "503")
                        },
                    },
                }
            },
            "/actions/{module}/{action}/validate": {
                **action_path,
                **post("Validate a declared action", "ActionRequest", "Validation", ("422",)),
            },
            "/actions/{module}/{action}/invoke": {
                **action_path,
                **post("Invoke a declared action", "ActionRequest", "Receipt"),
            },
            "/actions/{module}/{action}/batch": {
                **action_path,
                **post("Invoke a declared action over items", "BatchRequest", "BatchReceipt"),
            },
            "/audit/changes": post(
                "Committed changes, newest first", "ChangesRequest", "ChangesPage", ("409", "422")
            ),
            "/audit/loads": post(
                "Import loads, newest first", "LoadsRequest", "LoadsPage", ("409", "422")
            ),
            "/export": post(
                "A page of a module's graph as records, in a stable order, as the viewer",
                "ExportRequest",
                "ExportPage",
                ("409", "422"),
            ),
            "/query": post(
                "A read-only Weft statement over one named module, as the viewer",
                "QueryRequest",
                "QueryResult",
                ("422",),
            ),
        },
        "components": {
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {
                            **obj,
                            "properties": {
                                "type": {"type": "string"},
                                "message": {"type": "string"},
                                "reason": {"type": "string"},
                                "backend": {"type": "string"},
                                "operation": {"type": "string"},
                                "policy_code": {
                                    "type": "string",
                                    "pattern": "^[a-z][a-z0-9_]{0,63}$",
                                },
                                "token": {"type": "string"},
                                "construct": {"type": "string"},
                                "supported": {"type": "array", "items": {"type": "string"}},
                                "violations": {"type": "array", "items": obj},
                                "failures": {"type": "array", "items": obj},
                            },
                        }
                    },
                },
                "NotOperator": {
                    "type": "object",
                    "required": ["error", "reason"],
                    "properties": {
                        "error": {"const": "REFUSED"},
                        "reason": {"const": "not_operator"},
                    },
                },
                "Viewer": {
                    "type": "object",
                    "required": ["user", "modes"],
                    "properties": {
                        "user": {"type": "string"},
                        "modes": {
                            "type": "array",
                            "items": {"enum": ["user", "admin"]},
                            "minItems": 1,
                            "maxItems": 2,
                        },
                    },
                },
                "Version": {
                    **obj,
                    "properties": {
                        "contracts": {**obj, "additionalProperties": {"type": "integer"}}
                    },
                },
                "Revision": {
                    **obj,
                    "additionalProperties": {"type": ["integer", "string", "null"]},
                },
                "ActionRequest": {
                    **obj,
                    "properties": {
                        "inputs": obj,
                        "idempotency_key": {"type": "string"},
                        "expected_revision": {"$ref": "#/components/schemas/Revision"},
                    },
                },
                "BatchRequest": {
                    **obj,
                    "required": ["items"],
                    "properties": {
                        "items": {"type": "array", "items": obj, "minItems": 1, "maxItems": 100},
                        "atomic": {"type": "boolean"},
                        "stop_on_error": {"type": "boolean"},
                        "idempotency_key": {"type": "string"},
                        "expected_revision": {"$ref": "#/components/schemas/Revision"},
                    },
                },
                "ChangesRequest": {
                    **obj,
                    "properties": {
                        k: {"type": "string"}
                        for k in (
                            "module",
                            "type",
                            "key",
                            "by",
                            "action",
                            "group",
                            "since",
                            "until",
                            "after",
                            "provider",
                        )
                    }
                    | {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                },
                "LoadsRequest": {
                    **obj,
                    "required": ["module"],
                    "properties": {
                        "module": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "after": {"type": "string"},
                        "provider": {"type": "string"},
                    },
                },
                "ExportRequest": {
                    **obj,
                    "required": ["module"],
                    "properties": {
                        "module": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                        "after": {"type": "string"},
                    },
                },
                "ExportPage": {
                    **obj,
                    "properties": {
                        "items": {"type": "array", "items": obj},
                        "nextCursor": {"type": ["string", "null"]},
                        "omitted": {"type": "array", "items": {"type": "string"}},
                        "freshness": {"$ref": "#/components/schemas/Freshness"},
                    },
                },
                "QueryRequest": {
                    **obj,
                    "required": ["module", "sql"],
                    "properties": {
                        "module": {"type": "string"},
                        "sql": {"type": "string", "maxLength": 4000},
                        "params": obj,
                        "consistency": {"enum": ["latest", "bulk"]},
                        "at_least": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                },
                "QueryResult": {
                    **obj,
                    "properties": {
                        "columns": {
                            "type": "array",
                            "items": {
                                **obj,
                                "properties": {
                                    "name": {"type": "string"},
                                    "scalar": {"type": "boolean"},
                                    "type": {"type": "string"},
                                },
                            },
                        },
                        "rows": {"type": "array", "items": obj},
                        "truncated": {"type": "boolean"},
                        "freshness": {"$ref": "#/components/schemas/Freshness"},
                        "revision": {"$ref": "#/components/schemas/Revision"},
                    },
                },
                "Freshness": {
                    **obj,
                    "properties": {
                        "backend": {"type": "string"},
                        "asOf": {"type": "string"},
                        "at": {"type": "string"},
                        "consistency": {"type": "string"},
                    },
                },
                "Effect": {
                    **obj,
                    "required": ["kind"],
                    "properties": {
                        "kind": {"enum": ["create", "update", "delete", "link", "unlink"]}
                    },
                },
                "Receipt": {
                    **obj,
                    "properties": {
                        "action": {"type": "string"},
                        "refs": {"type": "array", "items": obj},
                        "created": {"type": "integer"},
                        "updated": {"type": "integer"},
                        "deleted": {"type": "integer"},
                        "linked": {"type": "integer"},
                        "unlinked": {"type": "integer"},
                        "token": {"type": "string"},
                        "group": {"type": "string"},
                        "replayed": {"type": "boolean"},
                    },
                },
                "Validation": {
                    **obj,
                    "properties": {
                        "ok": {"type": "boolean"},
                        "violations": {"type": "array", "items": obj},
                        "failures": {"type": "array", "items": obj},
                        "effects": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Effect"},
                        },
                        "replay": {
                            "oneOf": [{"$ref": "#/components/schemas/Receipt"}, {"type": "null"}]
                        },
                        "freshness": {
                            "oneOf": [{"$ref": "#/components/schemas/Freshness"}, {"type": "null"}]
                        },
                    },
                },
                "BatchReceipt": {
                    **obj,
                    "properties": {
                        "action": {"type": "string"},
                        "atomic": {"type": "boolean"},
                        "items": {"type": "array", "items": obj},
                        "succeeded": {"type": "integer"},
                        "failed": {"type": "integer"},
                        "token": {"type": ["string", "null"]},
                    },
                },
                "Change": {
                    **obj,
                    "properties": {
                        "group": {"type": "string"},
                        "at": {"type": "string"},
                        "by": {"type": "string"},
                        "action": {"type": "string"},
                        "module": {"type": "string"},
                        "ops": {"type": "array", "items": obj},
                        "backend": {"type": "string"},
                    },
                },
                "Load": {
                    **obj,
                    "properties": {
                        "load_id": {"type": "string"},
                        "initiated_by": {"type": "string"},
                        "at": {"type": "string"},
                        "module": {"type": "string"},
                        "created": {"type": "integer"},
                        "skipped": {"type": "integer"},
                        "rejected": {"type": "integer"},
                        "partial": {"type": "boolean"},
                    },
                },
                "ChangesPage": {
                    **obj,
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Change"},
                        },
                        "nextCursor": {"type": ["string", "null"]},
                        "truncated": {"type": "boolean"},
                        "freshness": {"$ref": "#/components/schemas/Freshness"},
                    },
                },
                "SchemaCatalogEntry": {
                    **obj,
                    "required": ["id", "title", "category", "path", "text", "format"],
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "category": {"const": "domain"},
                        "path": {"type": "string"},
                        "text": {"type": "string"},
                        "format": {"enum": ["json", "yaml"]},
                        "description": {"type": "string"},
                        "schemaFormat": {"enum": ["umf", "json-schema"]},
                    },
                },
                "SchemaCatalog": {
                    **obj,
                    "required": ["version", "entries"],
                    "properties": {
                        "version": {"const": 1},
                        "entries": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/SchemaCatalogEntry"},
                        },
                    },
                },
                "LoadsPage": {
                    **obj,
                    "properties": {
                        "items": {"type": "array", "items": {"$ref": "#/components/schemas/Load"}},
                        "nextCursor": {"type": ["string", "null"]},
                        "truncated": {"type": "boolean"},
                        "freshness": {"$ref": "#/components/schemas/Freshness"},
                    },
                },
            }
        },
    }


_STATUS_TEXT = {
    "400": "Invalid request",
    "401": "Not signed in or token expired",
    "403": "Refused, not offered, origin not allowed, or not an operator",
    "404": "Unknown or unreadable module or action",
    "405": "Wrong method",
    "409": "Conflict or not yet current",
    "413": "Body too large",
    "422": "A precondition failed",
    "429": "Too many requests in flight",
    "501": "Unsupported",
    "503": "Unavailable",
}
