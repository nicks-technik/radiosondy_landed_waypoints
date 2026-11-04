import toml
import sys
import os

def update_pyproject_version(new_version: str):
    pyproject_path = os.path.join(os.path.dirname(__file__), "pyproject.toml")
    
    try:
        with open(pyproject_path, "r") as f:
            data = toml.load(f)
    except FileNotFoundError:
        print(f"Error: pyproject.toml not found at {pyproject_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading pyproject.toml: {e}")
        sys.exit(1)

    if "project" not in data or "version" not in data["project"]:
        print("Error: 'project' or 'version' key not found in pyproject.toml")
        sys.exit(1)

    old_version = data["project"]["version"]
    data["project"]["version"] = new_version

    try:
        with open(pyproject_path, "w") as f:
            toml.dump(data, f)
        print(f"Successfully updated pyproject.toml version from {old_version} to {new_version}")
    except Exception as e:
        print(f"Error writing to pyproject.toml: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_version.py <new_version>")
        sys.exit(1)
    
    version_from_tag = sys.argv[1]
    # Remove 'v' prefix if present
    if version_from_tag.startswith('v'):
        version_from_tag = version_from_tag[1:]
    
    update_pyproject_version(version_from_tag)
