# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from wireup import DependencyContainer, create_container

from hop3 import services

container: DependencyContainer = create_container(
    # Let the container know where service registrations are located.
    service_modules=[services]
)
