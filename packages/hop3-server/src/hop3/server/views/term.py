# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from hop3.server.singletons import router, templates


@router.get("/term")
def term(request):
    """
    Terminal view.
    """
    ctx = {}
    return templates(request, "term.j2", ctx)
