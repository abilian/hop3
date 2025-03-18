# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

from wireup import DependencyContainer, create_container

from hop3 import services
from hop3.config import get_parameters

parameters = get_parameters()

container: DependencyContainer = create_container(
    # Parameters serve as application/service configuration.
    # parameters={
    #     "redis_url": os.environ["APP_REDIS_URL"],
    #     "weather_api_key": os.environ["APP_WEATHER_API_KEY"],
    # },
    # Let the container know where service registrations are located.
    service_modules=[services]
)
