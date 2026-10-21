"""The remote component's kind of record: how the phone reaches Clank (`config/remote.json`, design 0005 §4).

A change applies within a few seconds: the component's background task reads it each round, starting or stopping the
phone's listener and asking Tailscale to publish it or to stop.
"""

from pydantic import Field

from clank.kernel.records import Settings


class RemoteSettings(Settings):
    """How the phone reaches Clank."""

    KIND = "remote"
    LABEL = "Remote access"
    HELP = "Whether the phone page is on, where it listens on this machine, and the tailnet port Tailscale gives it."
    SINGLE = True

    on: bool = Field(
        False,
        title="On",
        description="Whether the phone page is published on your tailnet (decision 0012: off until you turn it on).",
    )
    port: int = Field(
        7721, ge=1024, le=65535, title="Local port", description="Where the phone's listener listens on this machine."
    )
    tailnet_port: int = Field(
        8445,
        ge=1,
        le=65535,
        title="Tailnet port",
        description="The HTTPS port Tailscale publishes the phone page on, on your tailnet only.",
    )
