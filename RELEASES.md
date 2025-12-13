# Release Process

This document describes how to create releases for the Bravia Quad Home Assistant integration.

## Automatic Release (Recommended)

1. Go to the **Actions** tab in GitHub
2. Select the **Release** workflow
3. Click **Run workflow**
4. Fill in the form:
   - **Version**: Enter the new version number (e.g., `1.0.1`)
   - **Release notes**: Optionally add release notes describing the changes
5. Click **Run workflow**

The workflow will:
- Validate the version format
- Update `manifest.json` and `__version__.py` with the new version
- Commit the version changes
- Create a Git tag
- Create a GitHub release

## Manual Release

If you prefer to create releases manually:

1. **Update the version** in `custom_components/bravia_quad/manifest.json`:
   ```json
   {
     "version": "1.0.1"
   }
   ```

2. **Update the version** in `custom_components/bravia_quad/__version__.py`:
   ```python
   __version__ = "1.0.1"
   ```

3. **Commit and push** the changes:
   ```bash
   git add custom_components/bravia_quad/manifest.json custom_components/bravia_quad/__version__.py
   git commit -m "Bump version to 1.0.1"
   git push
   ```

4. **Create a Git tag**:
   ```bash
   git tag -a v1.0.1 -m "Release v1.0.1"
   git push origin v1.0.1
   ```

5. **Create a GitHub Release**:
   - Go to the **Releases** page on GitHub
   - Click **Draft a new release**
   - Select the tag you just created (e.g., `v1.0.1`)
   - Add a release title (e.g., `Release v1.0.1`)
   - Add release notes describing the changes
   - Click **Publish release**

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR** version (X.0.0): Incompatible API changes
- **MINOR** version (0.X.0): New functionality in a backwards compatible manner
- **PATCH** version (0.0.X): Backwards compatible bug fixes

## HACS Integration

HACS will automatically detect new releases and make them available to users. After creating a release:
- HACS will show the new version in the integration list
- Users will be notified of available updates
- The release notes will be displayed in HACS

## Important Notes

- Always create a **full release**, not just a tag
- Release notes help users understand what changed
- Test the integration before creating a release
- Ensure GitHub Actions workflows pass before releasing
