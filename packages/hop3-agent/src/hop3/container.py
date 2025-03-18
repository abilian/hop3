from __future__ import annotations

from wireup import DependencyContainer, create_container

from hop3 import newconfig, services

parameters = newconfig.get_parameters()

container: DependencyContainer = create_container(
    # Parameters serve as application/service configuration.
    # parameters={
    #     "redis_url": os.environ["APP_REDIS_URL"],
    #     "weather_api_key": os.environ["APP_WEATHER_API_KEY"],
    # },
    # Let the container know where service registrations are located.
    service_modules=[services]
)
