"""Design 0002 §2.2 (decisions 0015, 0028): the TypeScript types of Clank's kinds are generated from their JSON
Schemas, as the API sends records (whole: every field present, defaulted ones too): strings, numbers, booleans,
nullable values, literal choices, arrays, maps, nested objects and references to definitions, each field with its
description."""

from typing import Any

from tools.tstypes import render, typescript_of


def test_simple_values_map_to_their_typescript() -> None:
    assert typescript_of({"type": "string"}) == "string"
    assert typescript_of({"type": "string", "format": "date-time"}) == "string"
    assert typescript_of({"type": "integer", "minimum": 1}) == "number"
    assert typescript_of({"type": "number"}) == "number"
    assert typescript_of({"type": "boolean"}) == "boolean"
    assert typescript_of({}) == "unknown"


def test_choices_nullable_values_and_references_map_to_unions_and_names() -> None:
    assert typescript_of({"enum": ["user", "clank"], "type": "string"}) == '"user" | "clank"'
    assert typescript_of({"const": "service/1"}) == '"service/1"'
    assert typescript_of({"anyOf": [{"type": "string"}, {"type": "null"}]}) == "string | null"
    assert typescript_of({"$ref": "#/$defs/Actor"}) == "Actor"


def test_arrays_maps_and_nested_objects() -> None:
    assert typescript_of({"type": "array", "items": {"$ref": "#/$defs/Step"}}) == "Step[]"
    nullable_items = {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "null"}]}}
    assert typescript_of(nullable_items) == "(string | null)[]"
    assert typescript_of({"type": "object", "additionalProperties": {"type": "integer"}}) == "Record<string, number>"
    assert typescript_of({"type": "object"}) == "Record<string, unknown>"
    assert typescript_of({"type": "object", "additionalProperties": True}) == "Record<string, unknown>"
    nested = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "integer"}}, "required": ["a"]}
    assert typescript_of(nested) == "{ a: string; b?: number }"


class Fake:
    """A kind as the generator reads it: its name, its class's name and its schema."""

    def __init__(self, kind: str, name: str, schema: dict[str, Any]) -> None:
        self.KIND = kind
        self.__name__ = name
        self.schema = schema

    def model_json_schema(self, mode: str = "validation") -> dict[str, Any]:
        return self.schema


def test_each_kind_and_each_definition_it_uses_becomes_one_interface_with_its_descriptions() -> None:
    actor = {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}
    kind = Fake(
        "question",
        "Question",
        {
            "type": "object",
            "description": "Something Clank asks the user.",
            "properties": {
                "id": {"type": "string", "description": "Its name."},
                "asked_by": {"$ref": "#/$defs/Actor"},
                "answer": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
            },
            "required": ["id", "asked_by"],
            "$defs": {"Actor": actor},
        },
    )
    shown = render([kind])
    assert "/** Something Clank asks the user. */\nexport interface Question {" in shown
    assert "  /** Its name. */\n  id: string;" in shown
    assert "  asked_by: Actor;" in shown
    assert "  answer: string | null;" in shown
    assert "export interface Actor {\n  kind: string;\n}" in shown
    assert "export interface RecordsByKind {\n  question: Question;\n}" in shown
    assert shown.count("export interface Actor") == 1


def test_a_kind_named_with_a_hyphen_is_a_quoted_key_of_the_records_by_kind() -> None:
    shown = render([Fake("model-file", "ModelFile", {"type": "object", "properties": {}})])
    assert '  "model-file": ModelFile;' in shown
