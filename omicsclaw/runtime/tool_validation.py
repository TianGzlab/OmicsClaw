from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ToolInputValidationResult:
    valid: bool
    message: str = ""
    normalized_arguments: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


def validate_arguments_against_schema(
    arguments: Any,
    schema: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(schema, Mapping):
        return []
    return _validate_value(arguments, schema, path="input")


def normalize_input_validation_result(
    value: Any,
) -> ToolInputValidationResult:
    if value is None:
        return ToolInputValidationResult(valid=True)
    if isinstance(value, ToolInputValidationResult):
        return value
    if value is True:
        return ToolInputValidationResult(valid=True)
    if value is False:
        return ToolInputValidationResult(valid=False, message="Tool input rejected.")
    if isinstance(value, str):
        text = value.strip()
        return ToolInputValidationResult(valid=not bool(text), message=text)
    if isinstance(value, Mapping):
        valid = bool(value.get("valid", False))
        return ToolInputValidationResult(
            valid=valid,
            message=str(value.get("message", "") or "").strip(),
            normalized_arguments=_normalized_argument_mapping(
                value.get("normalized_arguments")
            ),
            metadata=dict(value.get("metadata", {}) or {}),
        )
    raise TypeError(f"Unsupported tool input validation result: {type(value)!r}")


def _normalized_argument_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(
        f"normalized_arguments must be a mapping when provided, got {type(value)!r}"
    )


def _validate_value(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str,
) -> list[str]:
    issues: list[str] = []
    expected_type = schema.get("type")
    enum_values = schema.get("enum")

    if enum_values is not None and value not in list(enum_values):
        issues.append(
            f"{path} must be one of {list(enum_values)!r}; got {value!r}"
        )
        return issues

    if expected_type == "object":
        if not isinstance(value, dict):
            return [f"{path} must be an object; got {_type_name(value)}"]
        required = schema.get("required", []) or []
        for key in required:
            if key not in value:
                issues.append(f"{path}.{key} is required")
        properties = schema.get("properties", {}) or {}
        additional_properties = schema.get("additionalProperties", True)
        if additional_properties is False:
            for key in value:
                if key not in properties:
                    issues.append(f"{path}.{key} is not allowed")
        for key, nested_schema in properties.items():
            if key not in value:
                continue
            if isinstance(nested_schema, Mapping):
                issues.extend(
                    _validate_value(value[key], nested_schema, path=f"{path}.{key}")
                )
        return issues

    if expected_type == "array":
        if not isinstance(value, list):
            return [f"{path} must be an array; got {_type_name(value)}"]
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                issues.extend(
                    _validate_value(item, item_schema, path=f"{path}[{index}]")
                )
        return issues

    if expected_type == "string":
        if not isinstance(value, str):
            return [f"{path} must be a string; got {_type_name(value)}"]
        return issues

    if expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{path} must be an integer; got {_type_name(value)}"]
        return issues

    if expected_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [f"{path} must be a number; got {_type_name(value)}"]
        return issues

    if expected_type == "boolean":
        if not isinstance(value, bool):
            return [f"{path} must be a boolean; got {_type_name(value)}"]
        return issues

    return issues


def _type_name(value: Any) -> str:
    return type(value).__name__


__all__ = [
    "ToolInputValidationResult",
    "normalize_input_validation_result",
    "validate_arguments_against_schema",
]
