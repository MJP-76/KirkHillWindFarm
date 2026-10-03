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
4. **Update the version references in the docs.** Nothing fails when these go
   stale, so check them by hand every release:

   | Where | What it holds |
   |---|---|
   | `CHANGELOG.md` | a `## Version X.Y.Z` section, newest first |
   | `docs/installation.md` | "What's in the latest pre-release" names the latest stable |
   | `docs/development/review-brief.md` | version in the `Repo:` line, plus quoted line counts and symbol names |
   | `docs/development/decisions.md` | "Deployment state" version; the coordinator-split blocker |
   | `info.md` | example version in the SCADA version-badge bullet |
   | `AGENTS.md` | lint/CI claims and any line counts quoted from the code |
   | `TODO.md` | the release log section at the bottom |

   Verify the numbers instead of carrying them forward: `wc -l` for line counts,
   `grep` for symbol names, `stat -c %s` for file sizes. Symbols get renamed
   silently, so confirm each one still exists before leaving it in a doc.
5. Commit and push to `main`.
6. Tag and create a GitHub release:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   gh release create vX.Y.Z --title vX.Y.Z --generate-notes [--prerelease] --target <branch>
   ```

Release tags are generated as `vX.Y.Z` directly from `VERSION`.

[version-file]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/VERSION