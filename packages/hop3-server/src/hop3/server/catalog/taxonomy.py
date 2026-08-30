# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Taxonomy builder for categories and tags."""

from __future__ import annotations

from collections import defaultdict

from .models import CatalogApp, Category, Tag

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
    "Content Management": ["cms", "blog", "publishing", "website-builder"],
    "Business": ["erp", "crm", "accounting", "invoicing", "billing", "finance"],
    "Identity & Security": ["auth", "sso", "iam", "identity", "oauth", "oidc"],
    "News & Feeds": ["rss", "feeds", "feed-reader", "news", "aggregator"],
    "Monitoring": [
        "monitoring",
        "status",
        "uptime",
        "observability",
        "error-tracking",
        "alerting",
    ],
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
    "Content Management": "file-text",
    "Business": "briefcase",
    "Identity & Security": "shield",
    "News & Feeds": "rss",
    "Monitoring": "activity",
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
    "Content Management": "Websites, blogs, and publishing",
    "Business": "ERP, CRM, accounting, and invoicing",
    "Identity & Security": "Authentication, SSO, and identity",
    "News & Feeds": "RSS readers and feed aggregators",
    "Monitoring": "Uptime, status, and error tracking",
    "Other": "Other applications",
}


def get_category_for_app(app: CatalogApp) -> str:
    """
    The app's category: what it declares, else what its tags imply.

    An app's ``catalog.toml`` states its category, and that is the answer when
    it is present — the mapping below is a fallback for apps with no overlay,
    and it decides by whichever keyword happens to match first, which is no way
    to file an application someone has already filed by hand.
    """
    if app.category:
        return app.category

    for category, keywords in CATEGORY_MAPPING.items():
        for tag in app.tags:
            if tag.lower() in keywords:
                return category
    return "Other"


def build_categories(apps: list[CatalogApp]) -> list[Category]:
    """
    Build category objects from apps.

    Every recipe gets its ``category`` computed, including the alternative build
    paths, so an app page can show it whichever entry the reader arrived by.
    Only the default entry is listed *in* the category: browsing a category is
    browsing applications, and three routes to the same software listed side by
    side reads as three applications.
    """
    category_apps: dict[str, list[CatalogApp]] = defaultdict(list)

    for app in apps:
        category_name = get_category_for_app(app)
        app.category = category_name
        if app.is_default_variant:
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


def build_tags(apps: list[CatalogApp]) -> list[Tag]:
    """Build tag objects from apps."""
    tag_apps: dict[str, list[CatalogApp]] = defaultdict(list)

    for app in apps:
        if not app.is_default_variant:
            continue
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
