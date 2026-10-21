"""The notion component's kind of record (design 0010 §2-§3): Clank's connection to Notion, `config/notion.json`. The
integration's secret is not in it: it is a secret (`CLANK_HOME/secrets/notion/token`)."""

from pydantic import Field

from clank.kernel.records import Settings


class NotionSettings(Settings):
    """Clank's connection to Notion: where its API is, and which version of it Clank speaks."""

    KIND = "notion"
    LABEL = "Notion"
    HELP = (
        "Clank's connection to Notion (design 0010): its API and the version Clank speaks. The integration's secret is "
        "kept with the secrets (`clank notion connect`), never in this file."
    )
    SINGLE = True
    ON_CHANGE = "now"

    api: str = Field(
        "https://api.notion.com", title="Address", description="Notion's API (another address only for a test)."
    )
    version: str = Field(
        "2025-09-03",
        title="API version",
        description="The version of Notion's API Clank speaks (Notion-Version): 2025-09-03, in which a database holds "
        "data sources.",
    )
