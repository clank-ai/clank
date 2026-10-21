"""Design 0002 §2.2 and decision 0015: every settings kind's files have a JSON Schema generated from the kind's one
definition, carrying its fields' labels and help and the "schema" constant every file starts with."""

from clank.kernel.service_kinds import ServiceSettings
from tools.schemas import schema


def test_a_settings_kinds_schema_carries_its_fields_their_labels_and_help_and_its_schema_constant() -> None:
    generated = schema(ServiceSettings)
    assert generated["title"] == "Service"
    assert generated["properties"]["schema"]["const"] == "service/1"
    assert generated["required"][0] == "schema"
    assert generated["additionalProperties"] is False
    port = generated["properties"]["port"]
    assert (port["title"], port["default"]) == ("Port", 7720)
    assert port["description"]
