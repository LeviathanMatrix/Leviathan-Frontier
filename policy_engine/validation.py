from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def _load_schema(filename: str) -> dict[str, Any]:
    with (ROOT / filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_ref(schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"Unsupported ref: {ref}")

    node: Any = schema
    for part in ref[2:].split("/"):
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f"Invalid ref target for {ref}")
    return node


def _type_matches(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(
            value, bool
        )
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _validate_node(
    value: Any, schema_node: dict[str, Any], root_schema: dict[str, Any], path: str
) -> list[str]:
    if "$ref" in schema_node:
        schema_node = _resolve_ref(root_schema, schema_node["$ref"])

    errors: list[str] = []

    expected_type = schema_node.get("type")
    if expected_type and not _type_matches(expected_type, value):
        return [f"{path}: expected {expected_type}, got {type(value).__name__}"]

    if "const" in schema_node and value != schema_node["const"]:
        errors.append(f"{path}: expected const {schema_node['const']!r}")

    if "enum" in schema_node and value not in schema_node["enum"]:
        errors.append(f"{path}: expected one of {schema_node['enum']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema_node and value < schema_node["minimum"]:
            errors.append(f"{path}: value {value} below minimum {schema_node['minimum']}")
        if "maximum" in schema_node and value > schema_node["maximum"]:
            errors.append(f"{path}: value {value} above maximum {schema_node['maximum']}")

    if isinstance(value, str) and "minLength" in schema_node and len(value) < schema_node["minLength"]:
        errors.append(
            f"{path}: string length {len(value)} below minimum {schema_node['minLength']}"
        )

    if isinstance(value, list):
        if "minItems" in schema_node and len(value) < schema_node["minItems"]:
            errors.append(
                f"{path}: item count {len(value)} below minimum {schema_node['minItems']}"
            )
        item_schema = schema_node.get("items")
        if item_schema:
            for index, item in enumerate(value):
                errors.extend(
                    _validate_node(item, item_schema, root_schema, f"{path}[{index}]")
                )

    if isinstance(value, dict):
        properties = schema_node.get("properties", {})
        required = schema_node.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")

        if schema_node.get("additionalProperties") is False:
            extras = set(value.keys()) - set(properties.keys())
            for key in sorted(extras):
                errors.append(f"{path}: unexpected property {key!r}")

        for key, child in value.items():
            if key in properties:
                errors.extend(
                    _validate_node(child, properties[key], root_schema, f"{path}.{key}")
                )

    return errors


def validate_document(document: dict[str, Any], schema_filename: str) -> list[str]:
    schema = _load_schema(schema_filename)
    return _validate_node(document, schema, schema, "$")


def validate_aep_inputs(
    constitution: dict[str, Any], intent: dict[str, Any], risk_input: dict[str, Any]
) -> dict[str, list[str]]:
    return {
        "constitution": validate_document(constitution, "constitution.schema.json"),
        "intent": validate_document(intent, "intent.schema.json"),
        "risk_input": validate_document(risk_input, "risk_input.schema.json"),
    }
