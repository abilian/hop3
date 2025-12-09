# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Taxonomy builder for categories and tags."""

from __future__ import annotations

from collections import defaultdict

from .models import Category, MarketplaceApp, Tag

# Mapping of tag keywords to categories
CATEGORY_MAPPING = {
    "File Storage": [
        "files",
        "sync",
        "storage",
        "cloud-storage",
        "file-sharing",
        "dropbox",
        "drive",
    ],
    "Project Management": [
        "project-management",
        "kanban",
        "tasks",
        "task-management",
        "gantt",
        "scrum",
        "agile",
        "sprints",
    ],
    "Analytics": [
        "analytics",
        "statistics",
        "metrics",
        "tracking",
        "bi",
        "business-intelligence",
        "visualization",
    ],
    "Media": ["video", "media", "streaming", "photos", "images", "gallery"],
    "Documentation": ["wiki", "docs", "notes", "document", "markdown"],
    "Collaboration": ["collaboration", "chat", "teams", "slack", "webchat"],
    "Education": ["learning", "lms", "education", "edutech", "moodle"],
    "Productivity": [
        "calendar",
        "contacts",
        "mail",
        "caldav",
        "carddav",
        "scheduler",
        "appointments",
    ],
    "Forms & Surveys": ["survey", "polls", "forms", "feedback"],
    "Development": ["git", "code", "ci", "devops"],
    "Design": ["design", "prototyping", "figma"],
    "E-commerce": ["shop", "tickets", "ticketing"],
    "Translation": ["translation", "localization", "i18n", "l10n"],
    "Networking": ["vpn", "network"],
    "Database": ["database", "data", "no-code", "nocode"],
}

CATEGORY_ICONS = {
    "File Storage": "folder",
    "Project Management": "kanban",
    "Analytics": "chart-bar",
    "Media": "play-circle",
    "Documentation": "file-text",
    "Collaboration": "users",
    "Education": "graduation-cap",
    "Productivity": "calendar",
    "Forms & Surveys": "clipboard-list",
    "Development": "code",
    "Design": "palette",
    "E-commerce": "shopping-cart",
    "Translation": "globe",
    "Networking": "wifi",
    "Database": "database",
    "Other": "grid",
}

CATEGORY_DESCRIPTIONS = {
    "File Storage": "Store, sync, and share files securely",
    "Project Management": "Plan, track, and deliver projects",
    "Analytics": "Track metrics and visualize data",
    "Media": "Host and stream video and images",
    "Documentation": "Create and collaborate on documents",
    "Collaboration": "Communicate and work together",
    "Education": "Learning management and e-learning",
    "Productivity": "Calendars, contacts, and scheduling",
    "Forms & Surveys": "Collect feedback and responses",
    "Development": "Code hosting and CI/CD",
    "Design": "Design and prototyping tools",
    "E-commerce": "Online stores and ticketing",
    "Translation": "Localization and translation management",
    "Networking": "VPN and network tools",
    "Database": "Database and no-code platforms",
    "Other": "Other applications",
}


def get_category_for_app(app: MarketplaceApp) -> str:
    """Determine the primary category for an app based on its tags."""
    for category, keywords in CATEGORY_MAPPING.items():
        for tag in app.tags:
            if tag.lower() in keywords:
                return category
    return "Other"


def build_categories(apps: list[MarketplaceApp]) -> list[Category]:
    """Build category objects from apps."""
    category_apps: dict[str, list[MarketplaceApp]] = defaultdict(list)

    for app in apps:
        category_name = get_category_for_app(app)
        app.category = category_name
        category_apps[category_name].append(app)

    categories = []
    for name, cat_apps in sorted(category_apps.items(), key=lambda x: -len(x[1])):
        cat_id = name.lower().replace(" ", "-").replace("&", "and")
        categories.append(
            Category(
                id=cat_id,
                name=name,
                description=CATEGORY_DESCRIPTIONS.get(name, ""),
                icon=CATEGORY_ICONS.get(name, "grid"),
                apps=sorted(cat_apps, key=lambda a: a.title.lower()),
            )
        )

    return categories


def build_tags(apps: list[MarketplaceApp]) -> list[Tag]:
    """Build tag objects from apps."""
    tag_apps: dict[str, list[MarketplaceApp]] = defaultdict(list)

    for app in apps:
        for tag in app.tags:
            tag_apps[tag].append(app)

    tags = []
    for tag_name, tagged_apps in sorted(tag_apps.items(), key=lambda x: -len(x[1])):
        tag_id = tag_name.lower().replace(" ", "-")
        tags.append(
            Tag(
                id=tag_id,
                name=tag_name,
                apps=sorted(tagged_apps, key=lambda a: a.title.lower()),
            )
        )

    return tags


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    return text.lower().replace(" ", "-").replace("&", "and").replace("'", "")
