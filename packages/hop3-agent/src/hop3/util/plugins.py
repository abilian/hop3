import itertools
import os
from pathlib import Path
from types import ModuleType

from pluggy import PluginManager
import sys
from typing import List

pm = PluginManager("djp")
pm.add_hookspecs(hookspecs)
pm.load_setuptools_entrypoints("djp")


def _module_from_path(path: Path, name: str):
    # Adapted from http://sayspy.blogspot.com/2011/07/how-to-import-module-from-just-file.html
    module = ModuleType(name)
    module.__file__ = str(path)
    source = path.read_text()
    code = compile(source, path, "exec", dont_inherit=True)
    exec(code, module.__dict__)
    return module


plugins_dir = os.environ.get("DJP_PLUGINS_DIR")
if plugins_dir:
    for filepath in Path(plugins_dir).glob("*.py"):
        mod = _module_from_path(filepath, name=filepath.stem)
        try:
            pm.register(mod)
        except ValueError as ex:
            print(ex, file=sys.stderr)
            # Plugin already registered
            pass


class Before:
    def __init__(self, item: str):
        self.item = item


class After:
    def __init__(self, item: str):
        self.item = item


class Position:
    def __init__(self, item: str, before=None, after=None):
        assert not (before and after), "Cannot specify both before and after"
        self.item = item
        self.before = before
        self.after = after


def installed_apps() -> List[str]:
    return ["djp"] + list(itertools.chain(*pm.hook.installed_apps()))


def middleware(current_middleware: List[str]):
    before = []
    after = []
    default = []
    position_items = []

    for batch in pm.hook.middleware():
        for item in batch:
            if isinstance(item, Before):
                before.append(item.item)
            elif isinstance(item, After):
                after.append(item.item)
            elif isinstance(item, Position):
                position_items.append(item)
            elif isinstance(item, str):
                default.append(item)
            else:
                raise ValueError(f"Invalid item in middleware hook: {item}")

    combined = before + to_list(current_middleware) + default + after

    # Handle Position items
    for item in position_items:
        if item.before:
            try:
                idx = combined.index(item.before)
                combined.insert(idx, item.item)
            except ValueError:
                raise ValueError(f"Cannot find item to insert before: {item.before}")
        elif item.after:
            try:
                idx = combined.index(item.after)
                combined.insert(idx + 1, item.item)
            except ValueError:
                raise ValueError(f"Cannot find item to insert after: {item.after}")

    return combined


def urlpatterns():
    return list(itertools.chain(*pm.hook.urlpatterns()))


def settings(current_settings):
    # First wrap INSTALLED_APPS
    installed_apps_ = to_list(current_settings["INSTALLED_APPS"])
    installed_apps_ += installed_apps()
    current_settings["INSTALLED_APPS"] = installed_apps_

    # Now MIDDLEWARE
    current_settings["MIDDLEWARE"] = middleware(current_settings["MIDDLEWARE"])

    # Now apply any other settings() hooks
    pm.hook.settings(current_settings=current_settings)


def get_plugins():
    plugins = []
    plugin_to_distinfo = dict(pm.list_plugin_distinfo())
    for plugin in pm.get_plugins():
        plugin_info = {
            "name": plugin.__name__,
            "hooks": [h.name for h in pm.get_hookcallers(plugin)],
        }
        distinfo = plugin_to_distinfo.get(plugin)
        if distinfo:
            plugin_info["version"] = distinfo.version
            plugin_info["name"] = (
                getattr(distinfo, "name", None) or distinfo.project_name
            )
        plugins.append(plugin_info)
    return plugins


def to_list(tuple_or_list):
    if isinstance(tuple_or_list, tuple):
        return list(tuple_or_list)
    return tuple_or_list


def asgi_wrapper(application):
    for wrapper in pm.hook.asgi_wrapper():
        application = wrapper(application)
    return application
