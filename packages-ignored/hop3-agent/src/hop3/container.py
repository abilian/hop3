# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from wireup import create_sync_container

from hop3 import services

container = create_sync_container(
    # Let the container know where service registrations are located.
    service_modules=[services]
)
