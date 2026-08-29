# Release management

All release versions are tracked from a single source-of-truth file:
[`VERSION`][version-file].

## Branch strategy

- `main` — stable releases
- Pre-releases and stable releases are both published from `main`
- Release cadence can include both in sequence: a stable **Latest** tag, then a dev **Pre-release** tag
- Stable updates are always published as GitHub **Latest** releases
- Stable release flow includes a full merge into `main` before tagging/publishing

## Cutting a release

1. Update `VERSION` (use `X.Y.Z`, for example `4.5.2`).
2. Run `python scripts/version_sync.py sync` to update:
   - `custom_components/kirkhill_wind/manifest.json`
   - `pyproject.toml`
3. Validate with `python scripts/version_sync.py check`.
4. Commit and push to `main`.
5. Tag and create a GitHub release:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   gh release create vX.Y.Z --title vX.Y.Z --generate-notes [--prerelease] --target <branch>
   ```

Release tags are generated as `vX.Y.Z` directly from `VERSION`.

[version-file]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/VERSION