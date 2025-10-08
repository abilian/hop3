import importlib.metadata

try:
    entry_points = importlib.metadata.entry_points(group="hop3")
    if not entry_points:
        print("No entry points found for group 'hop3'.")
        print(
            "Check if the plugin is installed in editable mode (`pip install -e .`) in this environment."
        )
    else:
        print("Found entry points for group 'hop3':")
        for ep in entry_points:
            print(f"- Name: {ep.name}, Value: {ep.value}")
except Exception as e:
    print(f"An error occurred: {e}")
