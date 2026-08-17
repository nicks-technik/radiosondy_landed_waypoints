# Agent Guidelines

## Code Changes
- **Always Update Documentation**: After making any significant changes to the codebase (features, fixes, structure changes), immediately update the README.md and any relevant documentation files to reflect the new state. Documentation should always be in sync with the actual implementation.

- **Always keep the git repo (offline/online) up to date**: Commit changes frequently with clear, descriptive commit messages. Ensure all commits are pushed to the remote repository. Never leave uncommitted changes that affect functionality.

- **Use branches for new features**: When implementing new features, create a dedicated branch (e.g., `feature/gpx-icons`, `feature/multi-page-support`). Only merge to `main` after testing and code review. This keeps the main branch stable and allows for easy rollback if needed.

## Best Practices
1. Run linting (`ruff check .`) before committing
2. Run tests (`PYTHONPATH=$PWD pytest tests/ -v`) before pushing
3. Ensure CI passes before considering work complete
4. Keep dependencies minimal and remove unused ones
5. Maintain consistent code style and formatting
