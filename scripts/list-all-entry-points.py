import importlib.metadata
import sys
from collections import defaultdict


def list_all_entry_points():
    """
    Scans the current Python environment and lists all registered entry points,
    grouped by their entry point group name.
    """
    print(
        f"--- Scanning for entry points in Python environment: {sys.executable} ---\n"
    )

    try:
        # Get all entry points available in the environment
        all_eps = importlib.metadata.entry_points()
    except TypeError:
        # Handle older versions of importlib.metadata if necessary, though modern
        # versions should work with a single argument.
        print("Warning: Could not get all entry points at once. Trying group by group.")
        # This fallback is less common now but can be a good safety measure.
        # It's much slower as it has to scan for each group.
        # For simplicity, we'll focus on the modern API.
        print("This script requires a modern `importlib.metadata`.")
        return

    if not all_eps:
        print("No entry points found in this environment.")
        return

    # Group the entry points by their group name for readability
    grouped_eps = defaultdict(list)
    for ep in all_eps:
        grouped_eps[ep.group].append(ep)

    if not grouped_eps:
        print("No entry point groups found.")
        return

    # Print the results in a nicely formatted way
    print(f"Found {len(grouped_eps)} entry point groups:\n")

    for group_name in sorted(grouped_eps.keys()):
        print("=" * 60)
        print(f"GROUP: {group_name}")
        print("=" * 60)

        for ep in sorted(grouped_eps[group_name], key=lambda e: e.name):
            print(f"  - Name:  {ep.name}")
            print(f"    Value: {ep.value}")
            # The value is typically in the format "module.path:object_name"
            # Let's try to show where it's defined.
            try:
                dist = ep.dist
                if dist:
                    print(f"    From:  {dist.name} ({dist.version})")
            except Exception:
                # Some entry points might not have distribution info
                pass
            print("-" * 20)
        print("\n")


def check_specific_group(group_name: str):
    """Checks for entry points within a specific group."""
    print(f"\n--- Checking for specific entry point group: '{group_name}' ---")

    try:
        entry_points = importlib.metadata.entry_points(group=group_name)
        if not entry_points:
            print(f"-> RESULT: No entry points found for group '{group_name}'.\n")
            print("   This is likely why your plugin is not being discovered.")
            print(
                "   Ensure the plugin is installed in this environment (`pip install -e .`)."
            )
            print("   And that its `pyproject.toml` defines the correct group name.")
        else:
            print(
                f"-> RESULT: Found {len(entry_points)} entry point(s) for group '{group_name}':\n"
            )
            for ep in entry_points:
                print(f"  - Name: {ep.name}, Value: {ep.value}")

    except Exception as e:
        print(f"An error occurred while checking for group '{group_name}': {e}")


if __name__ == "__main__":
    # If a command-line argument is provided, check for that specific group.
    # Otherwise, list all groups.
    if len(sys.argv) > 1:
        specific_group = sys.argv[1]
        check_specific_group(specific_group)
    else:
        list_all_entry_points()
