# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""TOML loader for marketplace app metadata."""

from __future__ import annotations

import re
from pathlib import Path

import markdown
import tomllib

from .models import MarketplaceApp

# Markdown converter instance
_md = markdown.Markdown(extensions=["extra", "toc"])

# Pattern to match and remove the first H1 tag
_h1_pattern = re.compile(r"<h1[^>]*>.*?</h1>\s*", re.IGNORECASE | re.DOTALL)


def load_app(app_dir: Path) -> MarketplaceApp | None:
    """Load a single app from its directory."""
    toml_path = app_dir / "hop3.toml"
    if not toml_path.exists():
        return None

    try:
        with Path(toml_path).open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(f"  Warning: Skipping {app_dir.name} - TOML parse error: {e}")
        return None

    metadata = data.get("metadata", {})
    resources = data.get("resources", {})
    port_config = data.get("port", {})
    integration = data.get("integration", {})

    # Extract providers from [[provider]] sections
    providers = []
    for provider in data.get("provider", []):
        if "name" in provider:
            providers.append(provider["name"])

    app = MarketplaceApp(
        id=metadata.get("id", app_dir.name),
        title=metadata.get("title", app_dir.name.title()),
        description=metadata.get("description", ""),
        version=metadata.get("version", ""),
        upstream_version=metadata.get("upstream_version"),
        author=metadata.get("author", ""),
        website=metadata.get("website", ""),
        license=metadata.get("license", ""),
        tags=metadata.get("tags", []),
        memory=resources.get("memory"),
        port=port_config.get("web"),
        integrations=integration,
        providers=providers,
        source_path=str(app_dir),
    )

    # Compute resource tier
    app.resource_tier = app.compute_resource_tier()

    # Load readme if exists
    readme_path = app_dir / "readme.md"
    if readme_path.exists():
        app.readme = readme_path.read_text()
        _md.reset()
        html = _md.convert(app.readme)
        # Remove the first H1 (title is already shown in page header)
        app.readme_html = _h1_pattern.sub("", html, count=1)

    return app


def load_apps(apps_dir: Path) -> list[MarketplaceApp]:
    """Load all apps from the apps directory.

    Args:
        apps_dir: Directory containing app subdirectories with hop3.toml files

    Returns:
        List of MarketplaceApp objects
    """
    apps: list[MarketplaceApp] = []

    if not apps_dir.exists():
        return apps

    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        if app_dir.name.startswith("."):
            continue

        app = load_app(app_dir)
        if app:
            # Check for icon in app directory
            icon_path = app_dir / "icon.webp"
            if not icon_path.exists():
                icon_path = app_dir / "icon.png"
            if icon_path.exists():
                # Icon served via marketplace controller
                app.icon_url = f"/dashboard/marketplace/icons/{app.id}"
            apps.append(app)

    return apps
