from hop3_server.service.model import App


def list_apps() -> list[App]:
    return []


def get_app(app_name: str) -> App:
    return App(name=app_name)
