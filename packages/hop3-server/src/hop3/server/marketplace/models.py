# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Data models for Hop3 Marketplace."""

from __future__ import annotations

from dataclasses import dataclass, field

# Safe colors for fallback icons (good contrast with white text)
FALLBACK_COLORS = [
    "#3b82f6",  # blue
    "#10b981",  # emerald
    "#8b5cf6",  # violet
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#06b6d4",  # cyan
    "#ec4899",  # pink
    "#6366f1",  # indigo
    "#14b8a6",  # teal
    "#f97316",  # orange
    "#84cc16",  # lime
    "#a855f7",  # purple
]


@dataclass
class MarketplaceApp:
    """Represents an application in the marketplace.

    Named MarketplaceApp to avoid collision with hop3.orm.App.
    """

    id: str
    title: str
    description: str
    version: str
    author: str
    website: str
    license: str
    tags: list[str] = field(default_factory=list)
    memory: str | None = None
    port: int | None = None
    integrations: dict = field(default_factory=dict)
    providers: list[str] = field(default_factory=list)
    upstream_version: str | None = None

    # Computed fields
    category: str = ""
    resource_tier: str = "medium"
    icon_url: str | None = None
    readme: str = ""
    readme_html: str = ""

    # Path to source directory (set by loader)
    source_path: str = ""

    @property
    def initials(self) -> str:
        """Get 2-letter initials for fallback icon."""
        title = self.title.strip()
        if len(title) <= 2:
            return title.upper()
        return title[:2].capitalize()

    @property
    def fallback_color(self) -> str:
        """Get a consistent color based on app name hash."""
        # Simple hash using djb2 algorithm (fast, non-cryptographic)
        h = 5381
        for c in self.title:
            h = ((h << 5) + h) + ord(c)
        return FALLBACK_COLORS[h % len(FALLBACK_COLORS)]

    @property
    def memory_mb(self) -> int | None:
        """Parse memory string to MB."""
        if not self.memory:
            return None
        mem = self.memory.upper().strip()
        if mem.endswith("G"):
            return int(float(mem[:-1]) * 1024)
        if mem.endswith("M"):
            return int(mem[:-1])
        return int(mem)

    def compute_resource_tier(self) -> str:
        """Compute resource tier based on memory."""
        mb = self.memory_mb
        if mb is None:
            return "medium"
        if mb <= 256:
            return "light"
        if mb <= 512:
            return "medium"
        return "heavy"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "category": self.category,
            "resource_tier": self.resource_tier,
            "icon_url": self.icon_url,
            "initials": self.initials,
            "fallback_color": self.fallback_color,
        }


@dataclass
class Category:
    """Represents a category of applications."""

    id: str
    name: str
    description: str = ""
    icon: str = ""
    apps: list[MarketplaceApp] = field(default_factory=list)

    @property
    def app_count(self) -> int:
        return len(self.apps)


@dataclass
class Tag:
    """Represents a tag for applications."""

    id: str
    name: str
    apps: list[MarketplaceApp] = field(default_factory=list)

    @property
    def app_count(self) -> int:
        return len(self.apps)
