"""Typed settings for the example; reading configuration performs no host I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from arras.branding import Brand
from arras.distribution import DistributionConfig

ResourceName = Literal["seed.json", "graph.json"]


@dataclass(frozen=True)
class Settings:
    resource: ResourceName
    distribution: DistributionConfig


def settings(resource: ResourceName) -> Settings:
    return Settings(
        resource=resource,
        distribution=DistributionConfig(brand=Brand(name="Extension Host Example")),
    )
