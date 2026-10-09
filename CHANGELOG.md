# Changelog

All notable changes to the Kirk Hill Wind Farm integration.

## Version 4.15.2
- **Dashboard sign-in is parked, not removed.** Setup now goes straight to the API-key form. The sign-in path hands back a well-formed 56-character `kh_live_` key that the API rejects with `401 The API key is not valid.` — identical in length and format to a working key, and passed through byte for byte (`access_token` → `strip()` → `Authorization` header) — so the fault is server-side key activation upstream of us, and offering the option would send every new user into a dead end. The switch is a single documented constant, `SIGN_IN_ENABLED = False`, carrying that evidence in its comment.
- **Nothing was deleted.** `oauth.py`, `describe_key()`, the permission gate, the validation diagnostics, every string and every OAuth test remain in the tree and keep running in CI — so re-enabling later is one line plus a docs revert, not a rewrite, and none of it rots while parked.
- **Docs return to key-only instructions.** README, `installation.md` (pre-requisites, install step, Configuration) and `docs/index.md` no longer advertise sign-in; `installation.md` carries an explicit note on why it is unavailable and that it returns once the dashboard is fixed.
- **Tests.** 215 → 216: the "menu offers both paths" test became two — one asserting the flag is deliberately off and that setup lands on the API-key form, one flipping the flag and asserting both paths come back intact.

## Version 4.15.1
- **A sign-in rejection now reports the key's shape, so the two remaining explanations stop looking identical.** v4.14.2 established that the API answers `401 — The API key is not valid.` on a key `/oauth/token` had just issued and the dashboard lists as a valid connection — but that single error fits both "the dashboard rejected its own key" and "we sent the wrong bytes". The abort now appends `describe_key()`: length, a format verdict (`matches the kh_live_ API-key format` / `starts with kh_live_ but contains other characters` / `does not start with kh_live_`) and any whitespace at the edges. It **never returns a character of the key** — the only literal is `kh_live_`, which `oauth.md` publishes — and that property is asserted by test, because the string lands in a log line, an abort message and quite possibly a bug report.
- **Whitespace is stripped before the header is built.** A single trailing newline is enough for the API to answer "The API key is not valid." while every other part of the request is correct; stripping in `KirkHillApiClient.__init__` is cheaper than a release spent diagnosing it.
- **Tests.** 6 new (209 → 215), including direct assertions that key material never appears in the description.

## Version 4.15.0
- **New: member savings valued the way the board actually pays — per watt owned, not per kWh generated.** The board's Feb 2025–Jun 2026 announcement (£1.6m, 21p/W for 17 months) and the confirmation in discussion that *"time frame doesn't come into the calculation at all"* give `owned watts × rate ÷ 100`: **2,559.465 W × 21p = £537.49**, the figure the web dashboard shows (1,000 W → £210). The integration could only price generation (`kWh × p/kWh`), so nothing here could ever reproduce that number. The new `Member savings value` sensor reads the API's owner `capacity_watts` and multiplies it by a new **`Owner rate (p/W)`** `number` entity, persisted through `settings.merge_options` — deliberately with no `RestoreEntity` path, because the key is new and there is no pre-persistence value to recover (AGENTS.md rule 3, documented in the class).
- **No accrual, and an undeclared rate reads `unknown` instead of `£0.00`.** The payment is retrospective: the board reviews its finances and declares a payment when it declares one, so no effective earning rate exists until then — which is precisely why the web dashboard shows no ongoing earnings at all. The sensor therefore has no timeframe and derives no daily rate (the board's "15p per watt per 12 months" is an *equivalence for that one declaration*, not a rate to divide over time); while no rate is set it reports `unknown` with `projection_basis=no_rate_declared`, and `£0.00`/`no_capacity_zero` is reserved for genuinely having no watts to pay on. The generation-based `Value (…)` sensors are untouched — they answer a different question — and All time / past-year money stays `unknown`, because no rate history exists to value it with.
- **SCADA card: "Your Share (W)" is now "Your output (W)".** That row renders owner export power — live output, which sits near zero on a calm night — while "Your share" reads like the capacity savings are computed from, so the two were being compared as if they should match. Frontend JS, so this needs a real instance to confirm; CI runs no browser.
- **Docs.** `sensors.md` documents both entities and the two money questions; `decisions.md` records the capacity basis in the same commit.
- **Tests.** 9 new (200 → 209): the board's own numbers pinned (537.49, plus the 15p equivalence), generation proven never to enter the calculation, undeclared-rate and missing-capacity paths, and the rate persisting through `options`.

## Version 4.14.2
- **Diagnostics: a failed sign-in now says exactly why.** `oauth_key_invalid` was one opaque sentence covering three different failures (401, an HTTP error, an exception) and logged none of them — hit twice in the field with a key the dashboard had *just* issued and listed as a valid connection. `api.py` now reads the error body before raising, so a 401 carries the API's own words (`{"message": "The API key is not valid."}`), a 429/5xx carries **status and body** instead of a bare aiohttp string that read as "cannot connect", and an HTML proxy page still yields a snippet. The body is read exactly once — a failed `json()` decode would otherwise leave `text()` empty.
- **The reason is logged and quoted.** `_validate_api_key` returned silently for auth/connection failures; it now logs a warning with the verbatim reason and keeps it for the sign-in abort to quote through a `{detail}` placeholder — *"…could not be used to reach the API: The API key is not valid. Try signing in again…"*. Exception types are unchanged, so the coordinator's reauth-vs-hold-data behaviour is untouched.
- **Tests.** 8 new (192 → 200): 401 with a JSON body, 401 with an HTML body, a non-401 status carrying both halves, 403 quoting the permission message, the stored reason surviving a failed validation and clearing on a successful one, and the abort carrying the placeholder (plus its empty fallback).

## Version 4.14.1
- **Fixed: a key that may read only one scope was accepted at setup, and every denial it caused was reported as a connection error.** `client.test()` probed only `scope=owner` — the API's default — so a share-only or site-only key passed validation, created an entry, and stranded the other half of the sensors on the very next poll. Because `api.py` classified 403 through `raise_for_status()`, each of those denials then surfaced as `KirkHillConnectionError`: an endless "cannot connect" while the key itself was perfectly valid. Validation now asks for **both** scopes (the API exposes no permission field, so probing is the only way to know), and 403 is classified before `raise_for_status()`.
- **A permission failure is no longer mistaken for a dead key.** The new `KirkHillPermissionError` is deliberately *not* a `KirkHillAuthError`: a 401 means the key is dead and must start re-auth, whereas a 403 means the key may read less than the integration needs and re-entering it would fail identically. Setup and sign-in now name the consent option required — "My share and whole wind farm" — instead of blaming the key (`permission_required`, `oauth_permission_denied`), and at runtime the error falls into the coordinator's existing keep-last-known-data paths with **zero coordinator changes**, logging the scope and the reason.
- **Enforced on every path.** Sign-in, the paste form and re-auth all require a full-access key, which is as close as the integration can get to removing the dashboard's three consent choices without controlling that screen.
- **Tests.** 8 new (184 → 192). Three of the four API-client tests were confirmed to fail against the previous code (probe both scopes, classify 403, reject a share-only key), and a coordinator guard asserts a 403 never raises `ConfigEntryAuthFailed`.

## Version 4.14.0
- **New: sign in with your Kirk Hill dashboard account instead of pasting an API key.** The setup flow now opens with a menu — **Sign in with your Kirk Hill dashboard account (recommended)** or **I already have an API key**. Sign-in runs the dashboard's OAuth 2.1 authorization-code flow with PKCE: you approve access in the browser (your share, the whole wind farm, or both) and the integration receives a `kh_live_*` key that lands in exactly the place a pasted key always did. `entry.data` still holds connection details only, options are still written whole, and nothing downstream — API client, coordinator, dashboards, prices — changed, so existing installations are unaffected. The paste path is unchanged and stays the fallback whenever sign-in cannot run.
- **The OAuth client registers once per redirect URI, not once per login.** The redirect URI differs per install and per browser host, so a `client_id` cannot live in `manifest.json`: `POST /oauth/register` is called once per URI and cached in a Home Assistant `Store` (Nabu Casa installs all resolve to my.home-assistant.io's fixed URI). Endpoints come from `/.well-known/oauth-authorization-server` rather than being hard-coded, the registered URI is pinned across authorize/state/token, and every attempt mints a fresh PKCE verifier — the three things `oauth.md` asks of a client.
- **No refresh-token trap.** The token response's `expires_in: 7776000` is an *idle* window, not a token lifetime, and no refresh token is issued. The integration deliberately never builds HA's `OAuth2Session` — polling reads `entry.data[CONF_API_KEY]` directly — so there is no refresh path to fail at day 90. A key that really is dead still answers 401 into the existing re-auth flow.
- **A daily workflow now watches the upstream API for new features.** `OpenAPI sync` reads the dashboard's build stamp, and only when it moves downloads `openapi.yaml`, compares *parsed* content with the copy at the repo root, and opens a PR listing new endpoints, schemas and fields — running `test_openapi_contract.py` against the refreshed spec and putting its result in the PR body. It has already captured `GET /api/v1/carbon-avoided`, the `429 Too Many Requests` response on every endpoint, and the `Turbine` capacity pair.
- **Tests.** 23 new (161 → 184): 14 for the sign-in flow (register-once across two flows, discovery/registration failures reported and never cached, scope + `S256` + pinned redirect URI on the authorize URL, a fresh challenge per attempt, and both entry-shape guards) plus 9 from the scope-aware payload work.

## Version 4.13.9
- **Fixed: the owner £ sensor could read £0.00 beside a non-zero owner kWh reading.** Owner and site timeframe summaries are fetched separately, so a partial API failure can leave the owner frame absent while the site frame is present. The energy sensor handled that by deriving owner generation from `site generation × owner share`; the money sensor did not — it returned `None`, which `native_value` turns into **£0.00**, while its own attributes still reported `projection_basis: live_owner_price_pence_per_kwh`. Both now apply the same fallback, so they agree by construction (the new test measures it: 0.0 was shown where 13.4 belonged).
- **Fixed: two sensors raised `KeyError` on an empty owner payload.** `Capacity factor` and `Wind speed` subscripted `["summary"]` directly, but a scope that fails on its *first* poll is held as `{}` — and every other accessor in the package already used `.get("summary", {})`. Each state write raised until that scope recovered, while the rest of the integration was healthy.
- **Refactor.** The `total_generation_kwh` → `total_kwh` lookup now lives in `_summary_kwh` (introduced for v4.13.7's All time fix) and is used at all three sites instead of three inline copies — the duplication that let the owner paths drift apart.
- **Tests.** 4 new (`TestOwnerScopeDegradation`), each confirmed to fail against the previous code. The fourth asserts that an absence of data in *both* scopes still reads £0.00, so the fix cannot fabricate a figure.

## Version 4.13.8
- **Release tooling: `version_sync.py release` can finish now.** It created the local tag and passed it straight to `gh release create`, which refuses to publish a release from a tag that exists only locally ("... has not been pushed ..."), and its own "Tag already exists" guard then blocked every retry — cutting v4.13.7 had to be completed by hand with an explicit push plus `gh release create`. The tag is now pushed before the release is created (the order `release-management.md` documents), and the guard checks `origin` instead of the local tag list, so an attempt that died mid-way resumes while a published tag is still refused. Four tests, with `subprocess` stubbed.
- **Docs: the pre-release page named the wrong stable version.** It called v4.13.7 both active and stable after a blind string replace in the v4.13.7 sweep; it now lists v4.13.8 as the pre-release and v4.13.6 as the latest stable.
- **No integration code changes in this release.** `custom_components/` is identical to v4.13.7 — this release exists to prove the fixed release path end-to-end.

## Version 4.13.7
- **Fixed: a successful re-authentication never took effect, so the integration re-prompted for the API key forever.** The API client captures `entry.data` when the coordinator is built, so writing the new key into `entry.data` changed nothing: the next poll 401'd, `ConfigEntryAuthFailed` started a second reauth flow about a minute after the user had just completed one, and Home Assistant does not reload the entry for you on `reauth_successful` (only `async_update_reload_and_abort` does, and that helper reports usage when the entry has update listeners — an error from 2026.12). `_async_update_listener` now compares `entry.data` against a snapshot taken at setup and schedules a reload instead of refreshing — refreshing would poll with the stale key and restart the loop — and returns early while `runtime_data` is `None`, the window `async_unload_entry` opens.
- **Fixed: the integration's services could silently fail to register.** The domain services used the bare `hass.data` key `services_registered`, which another installed integration also uses. `hass.data` is global, so whichever integration loaded second skipped registration **with no log line**, leaving `kirkhill_wind.reload_integration` and `kirkhill_wind.reset_dashboard` non-existent — the SCADA card's Reload button and any automation calling them failed with "service not found". The key is domain-scoped now; the other integration needed no change.
- **Fixed: the Open-Meteo forecast task outlived a failed update.** `_fetch_timeframe_summaries` re-raises `ConfigEntryAuthFailed` when a summary answers 401, which stranded the forecast task created just above it — it kept running its retry sleeps in the background while asyncio reported "Task was destroyed but it is pending". The task is now cancelled and reaped on every exit path: summary failure, a cancelled update, and a forecast exception.
- **Fixed: a malformed Open-Meteo payload failed the whole update.** `_fetch_open_meteo_forecast` advertises "never fail core update", but its `except` tuple missed `ValueError`/`AttributeError`, so a payload it could not parse escaped at `await forecast_task` and every entity went unavailable for a poll. A forecast failure now logs a warning and drops to no-forecast; the slow-tier timer only advances when the update completes.
- **Fixed: All time generation was understated by a whole year when a year frame was missing.** A frame whose fetch failed is held as `{}` while it sits in retry backoff (up to an hour), and the sum skipped it silently — 24% low without 2024, 40% without 2025, 35% without the current year, measured against real data — while the attribute still claimed `sum_of_years`. An incomplete sum now falls back to the API's own `range=all` figure (~0.1% out, because that window trails the latest import) and says so: `generation_source=api_alltime_missing_years` plus `missing_year_frames`. The sum remains the normal path, so the card still adds up exactly.
- **`openapi.yaml` now describes the API that runs.** `CurrentSummary` and `Summary` *required* `site_capacity_watts`, which the API has never sent, while `additionalProperties: false` rejected the fields it does send: `capacity_watts`, `capacity_kw`, `total_power_watts`, `total_generation_kwh_today`, `total_generation_wh_today` and seven `co2_avoided_*` metrics. `CurrentTurbine` was missing the capacity pair and `latest_import_status` claimed `"completed"` where the API sends `"success"`/`"running"`. Corrected against a real diagnostics payload; no code changed — the integration was already reading the right keys.
- **Test fixtures split by endpoint, and pinned to the spec.** `conftest.py` put `generation_kwh`, `generation_share_percent`, `latest_rotor_speed_rpm` and `coordinates` on the `/api/v1/current` rows, which only `/api/v1/turbines` returns. Each endpoint now has its own rows, and the new `tests/test_openapi_contract.py` asserts every fixture against its schema in both directions — undocumented keys and unsatisfied `required` — so neither side can drift silently again.
- **Docs.** `decisions.md` records the All time degraded path (qualifying the 2026-09-29 sum decision) and that `main` now requires all three CI checks; `AGENTS.md`'s claim that no check blocked a merge was corrected after it cost a rejected push.
- **Tests.** 19 new (134 → 153): reauth, the listener's reload decision, forecast-task lifecycle (4), the OpenAPI contract (3), the All time year sum (4), service registration (3).

## Version 4.13.6
- **Fixed: a stale restore record could overwrite a saved price.** Since v4.13.0 `entry.options` is the authority, but `RestoreEntity` still applied its value on every start — inverted precedence. The read is now a **one-time backfill**, gated on a `CONF_PRICE_RESTORE_PENDING` marker written by the v9 config-entry migration: marker absent → `restore_state` is not read at all and options wins; marker present → the price is read, persisted, and the marker consumed. Config entry schema version 8 → 9.
- **No upgrade action needed, and no price is lost.** A price set before v4.13.0 existed only in `restore_state` — up to v4.11.6 `async_set_native_value` wrote nowhere — so that read was the only path carrying it forward. The backfill runs once for exactly those installations and never again. `0.0` remains a legitimate price (`projection_basis=no_owner_price_zero`), so nothing is retried on a value-equality guess.
- **Removed the invalid `license` key from `hacs.json`.** HACS validates that file against a closed schema, so `extra keys not allowed @ data['license']` had failed the HACS Validation job on every push since v4.13.1-pre added it. HACS reads the licence from GitHub's repository metadata, not from `hacs.json`. The `LICENSE` file is unchanged.
- **Docs.** `decisions.md` records the price-backfill rationale; `AGENTS.md` rule 3 now describes the one-shot form; `review-brief.md` updated. `TODO.md` corrected — the fallback default price is `0.0`, not 50.0.
- **Tests.** 16 new tests: 5 for the migration, 8 for the backfill, 3 for the steady-state guard.

## Version 4.13.5
- **Fixed: every timeframe summary was fetched twice per update.** `_fetch_timeframe_summaries()` ran once in the initial `asyncio.gather` and again after the turbine tier; because `_next_slow_update` is only advanced *after* the later call, both saw the slow tier as due. At the default 60-second scan interval that is roughly 2,880 redundant requests a day, plus 14 extra on each hourly slow poll. Summaries are now fetched once, after the turbine tier has refreshed the cached coordinates the Open-Meteo forecast needs.
- **Fixed: a malformed API payload raised an unrecoverable `AttributeError`.** `_parse_data()` validated the envelope but returned whatever `body["data"]` held, so a `{"data": []}` response blew up inside the client instead of raising a `KirkHillApiError` the coordinator can recover from — in `get_turbines()` this happened before that method's own guard, so stale-data handling and retry backoff never engaged. The `dict` guarantee is now enforced, with distinct messages for a non-object body, a missing `data` key, and a non-object `data`.
- **Test fix.** The coordinator schedule test asserted on a *set* of `(scope, range)` pairs, and a set is invariant under duplication — it passed identically against the buggy and the correct code, which is how the doubled fetch reached a stable release. Assertions are now count-based, and `TestApiCallBudget` pins the budget across the first poll (18 calls), a steady-state fast poll (2), a turbine-due poll (2), a slow-tier poll (14) and completed-year caching, with expectations derived from the timeframe constants rather than hardcoded.
- **Docs.** `AGENTS.md` gained the seven do-not-break invariants, each naming its regression test; `docs/development/decisions.md` added with ten entries on the config-entry schema, coordinator tiers and year cache; `review-brief.md` had stale version references corrected.
- **Not included: `ruff` and coverage thresholds.** The 40 existing `E501`s would fail the build on day one, so those are separate changes.

## Version 4.13.4
- **Removed clip paths, increased viewBox width.** Clip paths were masking text overflow instead of fixing it. Removed all clip paths and increased `wMax` from 1800 to 2200 so the SVG viewBox grows to fit the pill text content naturally.

## Version 4.13.3
- **Widened SCADA card pills.** Version (150→170), API status (68→78), alarm (110→130), and wind speed (240→280) pills are wider to fit text content without clipping.

## Version 4.13.2
- **Fixed: SCADA card text overflow on first load.** Pill rectangles (version, API status, alarm, wind speed) and generation panels (owner, site) now have SVG clip paths that prevent text from extending beyond the rect bounds. This eliminates the first-load layout shift where overflowing text triggered a viewBox recalculation.

## Version 4.13.1
- **New diagnostic sensors (#54).** Five fields the API already returned but the integration discarded are now exposed:
  - `binary_sensor.data_complete` — on when every turbine has current power, wind speed, and state data.
  - `sensor.data_generated_at` — timestamp of when the API response was generated (data freshness).
  - `sensor.unknown_turbines` — count of turbines with no imported state.
  - `sensor.latest_import_status` — status of the latest data import (e.g. `completed`), with `latest_generation_interval_end` as an attribute.
  - Rotor speed sensor now includes a `sampled_at` attribute showing when the rotor speed was last measured.
- **API call optimisation.** Removed the redundant `/api/v1/wind-speed` call — wind speed is already in the `current` endpoint summary. Saves 6 API calls/hour. Completed calendar year summaries (`year_2024`, `year_2025`, …) are now cached on first fetch and never refetched, saving 4 calls/hour (growing by 2 each year).
- **Open-Meteo forecast parallelised.** The forecast now runs as a parallel task alongside the timeframe summary fetches when the slow tier is due, instead of sequentially after. Uses cached turbine coordinates so it does not depend on a fresh turbine fetch.
- **Dashboard robustness.** `url_already_exists` detection now checks the exception's `translation_key` attribute instead of string-matching the translated message, protecting against future HA translation changes.
- **Docs: pre-release install and feedback section.** Installation page now covers enabling pre-releases in HACS, downloading a specific pre-release version, and reporting pre-release problems with the required version details.
- **Docs: sensor reference updated.** Added API Status binary sensor, Data complete binary sensor, Data generated at, Unknown turbines, Latest import status, and Owner share sensor. Fixed "State text" → "State" to match the actual entity name.
- **Docs: review-brief updated.** Version reference corrected to v4.13.0; removed stale projected-earnings options from OptionsFlow description.
- **Docs: SUPPORT and CONTRIBUTING files added.**
- **Test fix.** `test_obsolete_card_removed` no longer depends on non-deterministic set iteration order.

## Version 4.11.7
- **Removed: projected annual earnings.** The setup/options fields, the `Projected annual earnings (Owner/Site)` number entities, and the `projected_annual_gbp` / `projection_factor` attributes are gone. They were estimated averages (default £132 / £0) feeding a projected model retired in v4.11.5 — earnings are now `kWh × real price`, or `£0.00` when no price is set, so the estimates drove no displayed value. Existing installations migrate automatically (config version 7 strips the stale keys). Prices remain editable via the number entities and the dashboard price pills.
- **Fixed: past-year £ suppression now covers future years.** The suppression check matched only `year_2024`/`year_2025` literally; a future `year_2026` frame would have shown a £ figure revalued at today's price — exactly the misvaluation the suppression exists to prevent. Any `year_YYYY` frame is now suppressed automatically.
- **Removed dead code:** the unused `_cfd_price_gbp_per_mwh()` helper.

## Version 4.11.6
- **All time generation is now calculated from the per-year figures.** The All time kWh equals `2024 + 2025 + … + the current year to date` exactly, instead of trusting the API's separate `range=all` total. The `sum_of_years_kwh` attribute lists the per-year components, and `generation_source` reads `sum_of_years`.
- **Future years join automatically.** The per-year timeframe list is derived from the commissioning year (2024) to the last complete year, so a new year is fetched and summed as soon as it completes — no code changes needed. Its sensors appear after the next restart.
- **Past-year figures are sensors only.** `Generation (2025)` / `Generation (2024)` (owner and site) remain available as entities but are no longer wired into the SCADA card's generation/finance panels — the card shows Yesterday, Today, Week, Month, YTD, Year and All time as before.

## Version 4.11.5
- **Two independent price entities.** The single price model is split into:
  - `number.<farm>_owner_price_p_kwh` — **Owner price in p/kWh** (enter `6` for 6 pence). Drives the owner £ figures.
  - `number.<farm>_negotiated_price_gbp_mwh` — **Site/CfD price in £/MWh** (CfD-style strike price). Drives the site £ figures.
  - Both default to `0.0`; sensors read `£0.00` until a real price is set (issue #58 — no projected-model fallback). Displayed figures never round up (`0.06` shows as `0.06`).
- **Price pills on the SCADA card.** Click the price pill on the Owner or Site title row to edit the price inline (opens a modal writing `number.set_value`). Hint: "Earnings are live generation × this price, updated on the next poll cycle."
- **Live £/h rate on the Power rows.** Owner: `ownerExportKw × ownerPrice(p/kWh) ÷ 100`; Site: `sitePowerMw × sitePrice(£/MWh)`. Shows `—` until a price is set.
- **Past-year generation sensors.** New `Generation (2025)` / `Generation (2024)` sensors (owner and site) hold live kWh from the API (`range=YYYY` queries). They are sensors only — **not shown on the SCADA card**. More years appear automatically as time passes.
- **Past-year and All-time £ values are suppressed (`—`).** The API records energy only, never money, so applying today's price to history would silently revalue it every time the price is edited. Stands until the CfD strike price value(s), whether the CfD has ever changed, and its contract length are confirmed. kWh figures stay live. This is the foundation for the future multi-CfD price schedule.
- **Fixed: the All time row never updated its values.** The card derived row keys from the display name with spaces replaced by hyphens (`All time` → `gen-all-time`), but the DOM row is keyed `gen-alltime` — a mismatch that left the row stuck at `—` since v4.8.41. Row keys now strip spaces instead; all rows update correctly.
- **Version strings unified.** `VERSION`, `manifest.json`, `pyproject.toml` and `KIRKHILL_WIND_SCADA_VERSION` had drifted apart (4.11.2 / 4.11.5 / 4.11.2 / 4.11.4). All are now synced from `VERSION` via `scripts/version_sync.py`.

## Version 4.11.4
- **Site panel portrait fix:** "Capacity Factor" label no longer overwritten by the value. The label (which already duplicated the unit — the value carries its own `%`) was long enough to collide with the amber value text on narrow layouts; shortened to `Capacity Factor`.
- **Owner panel value styling:** "Your Share (W)" is now amber and 16px like every other figure in the panel (was green/success-coloured and larger).

## Version 4.11.3
- **Trailing zeros on the last two chart axes fixed.** The Site Power (MW) chart (Site Generation & Capacity panel) and Export Power (MW) chart (National Grid panel) were rendering raw recorder values on the y-axis (`0.000000` / `0.00000000000000`). Both now use `_fmt(v, 2)` axis formatters, stripping trailing zeros like every other chart.
  - This completes the trailing-zeros sweep from v4.11.1/v4.11.2: kWh, kW, %, RPM and m/s axes were already formatted — these two MW line charts were the only remaining raw-value axes.

## Version 4.11.2
- **Daily energy-chart totals fix:** `_fetchDailyStatistics` now uses `state: r.state ?? r.sum` — the recorder's `sum` statistic for daily-reset counters equals `state − K` (constant offset, never reset), so using `sum` produced negatives/garbage. `state` is the correct daily-reset total.
- **Chart y-axis formatting across all timeframes:** Added formatters to eliminate trailing zeros on 1M/6M/1Y axes.
  - kWh charts (Site, Grid, Owner, Turbine — bar & step-line): `_kwhAxis()` helper with thousand separators (`266,242` instead of `266242`).
  - Turbine Power (kW), Capacity (%), Rotor (RPM), Wind (m/s): per-unit formatters.
  - Owner Power (kW), Site Capacity (%): formatters added.
  - Scatter chart (Wind vs Power) already had formatters.

## Version 4.10.0
- **National Grid detail modal.** Click the National Grid box to open a pop-out showing:
  - Current Export (MW) and Today To Grid (kWh) KPI cards.
  - Historical Export Power chart (MW over time) — shows instantaneous power at each point in time, not cumulative energy.
  - Historical Energy To Grid chart (kWh over time) with daily reset filtering.
  - Timeframe selector (6H, 12H, 24H, 1W, 1M, 6M, 1Y).
- **Grid labels renamed.** "Export" → "Current Export", "To Grid Today" → "Today To Grid" for clarity.
- **Consistent colour scheme across dashboard.** Semantic colours now match everywhere:
  - Amber (`--khscada-power-color`) = power/energy values (t-power, t-today, grid-power, grid-energy, Owner/Site generation).
  - Cyan (`--khscada-wind-color`) = wind speed (t-wind, wind-value, chip-value).
  - Green (`--khscada-success-color`) = financial values and OK status (Owner/Site £, alarm OK, API OK).
  - Primary = titles, capacity, labels (t-id, t-op, grid-title, Owner/Site titles).
  - Secondary = descriptive labels and metadata (t-label, t-last, chip-label, grid-label).
- **Turbine box layout improvements:**
  - Capacity line moved to first position in turbine boxes.
  - Generation, Today, Wind, Rotor, Since follow in order.
  - Status pill height increased to22px with16px gap below to prevent text overlap.
- **Font styling consistency.** Turbine text now matches Owner/Site card pattern:
  - Values (t-power, t-today, t-op, t-wind, t-detail) = semibold, primary colour.
  - Labels (t-label) = regular, secondary colour.
  - Metadata (t-last) = regular, secondary colour.
- **Energy chart reset filtering.** All cumulative energy charts (Grid, Owner, Site, Turbine) now filter out daily counter resets that previously caused trailing 0s on1m,6m,1y timeframes.
- **Font scaling fixes.** VIEWBOX height bounds adjusted (hMin700, hMax1900) to allow proper vertical flex. Font scale capped at min(1, scaleX) to prevent text overflow.
- **Dashboard fills screen.** ha-card height restored to calc(100vh -64px) to ensure proper viewport filling.

## Version 4.9.0
- **SCADA card top chip row redesign.** The chip row is reordered and enhanced:
  - Refresh button moved to first position.
  - Version pill shows `Running: vX.Y.Z  Latest: vX.Y.Z` from the HACS update entity, with amber border when an update is available.
  - API status pill now flashes red when offline (matching turbine fault behavior); three-tier system ready for rate limiting (green OK, amber rate-limited, red down) when the API exposes `rate_limited` attribute.
  - Turbine status pill merged with alarm: shows `X Turbines Active` with three-tier colors (green all active, amber some offline, red all off + flash).
  - Wind Speed chip moved to top row as a single line: `Wind Speed: Current X.X m/s  Forecast: X.X m/s`.
  - All pills use `<tspan>` elements for label+value flow — no white space gaps at any card width.
  - Legend strip removed (status colors are self-explanatory from per-turbine badges).
- **Turbine status pop-out.** Click the turbine status pill to see per-turbine status with color dots, timestamps, and expandable history (last 24h, last 8 status changes per turbine).
- **API status pop-out.** Click the API pill to see current status, since timestamp, entity ID, and recent history (last 10 status changes with durations).
- **Card height tightened.** VIEWBOX height locked to 1300px (hMin=hMax) to eliminate bottom white space after legend removal.
- **Generation panels repositioned.** Owner and Site panels sit directly under the pill line with consistent spacing.
- **Grid box aligned.** National Grid box positioned at the bottom of the turbines section, aligned with bus bar end.
- **Rate limiting groundwork.** Frontend wired for `rate_limited` attribute on API status entity — amber "API LIMITED" state activates when exposed. Issue draft ready for API developer requesting 429 + Retry-After responses.
- **Turbine map placeholder.** Temporary empty `kirkhill-wind-turbine-map.js` file added to prevent stale Python module crash on integration reload (the module still references the deleted file until next HA restart).

## Version 4.8.81
- **API resilience hardening.** A batch of changes from the fifth external
  review that make the integration keep working through API hiccups instead of
  blanking out:
  - Polls now share Home Assistant's HTTP session instead of opening a fresh
    connection pool each poll (also used for config-time API-key validation).
  - The fast-path `current` fetch is now **failure-tolerant per scope** — when
    one scope's fetch fails the last-known-good values are kept and marked
    stale rather than the whole tick being lost. A failed key still raises
    `ConfigEntryAuthFailed` so re-auth is prompted.
  - The per-turbine (today / all) fetches now run in **parallel**, and one
    failing turbine no longer takes the whole farm down — last-known turbine
    data is kept.
  - The wind-speed series is primed on the very first tick instead of being
    skipped until the second refresh.
  - A 200-level error body now raises a proper API error instead of a raw
    `KeyError`; the calendar-year range uses HA's local time (not UTC) and
    Open-Meteo retries use exponential backoff.
- **Turbine map card is now deprecated.** The standalone
  `kirkhill-wind-turbine-map` custom card — retired from the dashboard when the
  Turbines tab was removed in v4.8.80 — now shows a visible **deprecation
  banner** at the top of the card, pointing to the **Kirk Hill SCADA** card for
  live per-turbine status, power, and generation today. The card can no longer
  be added through the dashboard editor and will be **removed in a future
  release**; the bundled file and its Lovelace registration stop shipping at
  that point.
- **Wind Speed detail modal.** Clicking the **Wind** panel on the SCADA card
  opens a modal showing current wind speed, the one-hour forecast, and the
  live difference between them — alongside the existing Site and Owner detail
  modals. The wind panel now shows a cursor/hover affordance like the other
  clickable panels.
- **Turbine activity timeline becomes a labelled swimlane.** The turbine
  detail modal's activity history rows are now organised as a **swimlane chart
  with one labelled row per state** the turbine was in during the window
  (running, curtailed, stopped, faults, etc.), so state changes and their
  durations read at a glance. Hovering a state band shows its start/stop time
  and duration.
- **SCADA numbers no longer show trailing zeros.** Values like `617.0` now
  render as `617`, while mid-decimal values such as `617.5` are unchanged.
- **SCADA right-hand column alignment.** The grid panel and the Wind / Owner
  generation / Site generation chips are re-scaled and re-aligned against the
  right edge of the diagram for tidier column edges.

## Version 4.8.80
- **Turbines tab removed.** The standalone Turbines view is deleted — the
  per-turbine status overview, and the associated view-level deprecation banner
  no longer ship. Live per-turbine status, power, and
  generation today are already shown inside the **SCADA** card, and per-turbine
  history lives in the turbine detail modals, so the standalone view was
  redundant. Dashboards with the old `turbines` view are pruned automatically
  on merge. The standalone turbine map custom card is still bundled so existing
  manual placements keep rendering, but it is deprecated as of v4.8.81 (see
  above).
- **Dashboard tab renamed to "Kirk Hill SCADA".** The auto-generated dashboard
  is now a single-tab view titled **Kirk Hill SCADA** (was "SCADA"), ready to
  grow as the hub for multiple co-op wind-farm SCADA dashboards.
- **Coordinates link to Google Maps.** In each turbine's detail modal, the
  Coordinates row is now a link that opens Google Maps at the turbine's
  position.
- **Negotiated CfD price entity.** A new `number.<farm>_negotiated_price_gbp_mwh`
  entity lets you set the negotiated (CfD) price in GBP/MWh. When a price is
  set, the £ value column is calculated from **actual generation** (kWh ÷ 1000
  × price) instead of the projected model — financial figures become
  live-accurate per timeframe. When the price is 0 (default) or live generation
  is unavailable, the existing projected model is used as a fallback, so
  existing installs are unchanged until a price is entered.
- **SCADA panel polish.** Panel headers simplified to **Owner** / **Site**
  (was "Owner Capacity" / "Site Capacity"). Gen/value fonts unified at 14px to
  match the Owner card, and the Timeframe / Generation / Value (£) columns were
  tightened and right-aligned so the rows sit closer together.

## Version 4.8.79
- **Finances tab retired — financials are now in the SCADA card.** The
  standalone Finances view is removed. Today's earnings, this month, and YTD
  figures are replaced by a **£ value column** on every timeframe row
  (Yesterday…All time) in both the **Owner Capacity** and **Site Capacity**
  panels of the SCADA card, alongside the kWh figures. Both Owner and Site
  values are shown.
- **SCADA panels renamed and headed.** The right-side panels are now headed
  "Generation, Capacity & Earnings" and titled **Owner Capacity** and
  **Site Capacity** (formerly "Owner/Site Generation & Capacity").
- **Compact table layout with column headings.** Each panel now has a
  **Timeframe / Generation / Value (£)** column heading row, and the rows are
  tightened (smaller value type, closer row spacing, two columns brought
  together) so the financials don't look spread out.
- **Map tiles back to OpenStreetMap.** The turbine map reverts from the CARTO
  Voyager experiment to the standard `tile.openstreetmap.org` source for
  reliability on all networks.
- **SCADA chrome: reset button moved after the API pill.** The bottom row now
  reads version | API status pill | reload button. The "Status since" text in
  turbine cards was darkened to match the wind/today lines for readability.

## Version 4.8.78
- **Waiting-for-data overlay no longer sticks.** The placeholder was written as
  text inside the chart container, so ApexCharts left it sitting on top of a
  finished graph. It is now a separate overlay that is removed when the charts
  render.
- **Chart tooltips follow the HA theme.** Turbine/Owner/Site ApexCharts use
  dark/light tooltip, axis and grid colours from the active theme instead of a
  white box with grey text.
- **6M / 1Y charts use hourly statistics.** Windows longer than a week pull
  recorder hourly means (capped at 500 points) instead of raw history, so a
  slow browser is not dragging months of every state-change.

## Version 4.8.77
- **Dashboard consolidation — deprecation banners.** The Finances and Turbines
  views now carry a "View being deprecated — migrated to the SCADA Dashboard,
  not under development" banner at the top, linking to the SCADA tab.
- **History tab removed.** Its three 25-hour owner/site power + wind charts were
  superseded by the SCADA card's Owner and Site pop-out modals with selectable
  6H–1Y timeframes. The tab is gone; the data is available through those modals.
- **Turbines tab trimmed.** Per-turbine status cards (T1–T8) and the all-turbine
  activity graph removed — turbine power, status, and activity history are now
  shown on the SCADA diagram and in each turbine's pop-out modal. The turbine
  map remains (CARTO Voyager tiles), under the deprecation banner.
- **Options: "Turbine activity chart timeframe" removed.** The `graph_hours`
  option only fed the removed Turbines activity graph and is gone from the
  options flow and translations.

## Version 4.8.76
- **SCADA bottom chrome: API pill next to version, above legend.** The API
  status pill, version number and reload button now sit together on a single
  row above the legend strip. The version text is slightly darker for better
  contrast.
- **Turbine activity history chart.** The turbine detail modal now includes a
  horizontal status timeline covering the selected timeframe, showing at a
  glance when a turbine was running, curtailed, in maintenance, stopped, etc.
- **Turbine map: switch tile source to CARTO Voyager.** The map was loading
  tiles from tile.openstreetmap.org, which blocks unidentified embedded
  applications (osm.wiki/blocked). Tiles now come from CARTO's free Voyager
  layer, which uses OSM data under a more permissive policy for embedded use.

## Version 4.8.75
- **API Status pill on the SCADA card.** The header now shows an "API" chip
  that is green with "API OK" while the Kirk Hill API responds and red with
  "API DOWN" when the coordinator's last update failed, instead of hiding the
  outage behind a page full of unknown values. Driven by a new
  `binary_sensor.<farm>_api_status` (device class connectivity) that reflects
  the coordinator's last fetch outcome.

## Version 4.8.74
- **Fix the turbine "Generation Today" chart not rendering.** The generation
  step-line charts (turbine, site and owner modals) used `type: "stepLine"`,
  which ApexCharts does not recognise as a chart type, so the charts stayed
  blank. They are now regular line charts with a `stepline` stroke, so the
  running kWh total draws correctly.
- **Reset the turbine chart timeframe to 24h when the modal is closed.** A
  selected 6M/1Y window no longer persists after leaving the turbine detail, so
  reopening does not re-fetch months of history every time. Timeframe changes
  still apply while the modal is open.
- **Tidy the "Wind vs Power" scatter axes.** Axis labels are formatted to two
  decimals so kW/m/s values no longer sprawl across many zeros.
- **"Waiting for data…" indicator.** While the history for the selected window
  is loading (this is slower for longer timeframes), the chart area shows a
  waiting message instead of looking frozen.

## Version 4.8.73
- **Debug logging on every API request.** Each Kirk Hill API call now logs its
  endpoint, query params and round-trip latency at debug level, and failures
  log the path and elapsed time before the exception is raised — so rate-limit
  or slow-response windows are visible in the debug log.
- **Coordinator logs what it fetches and why.** Each tick logs the summary
  timeframes due (fast tier, hourly slow tier, or a backoff retry), and every
  summary result logs its scope, timeframe and whether it was previously stale,
  at debug level.
- **Diagnostics download now shows the stale/retry state.** The config-entry
  diagnostics include the coordinator tick, per-timeframe `summary_stale`
  flags, consecutive failure counts, and the tick each timeframe is due for
  retry — so a reporter's download shows exactly which timeframes were blanked
  or stale and whether backoff was still pending.

## Version 4.8.72
- **Keep last-known data during API outages, marked as stale.** When the
  upstream summary fetch fails, the generation/capacity values are no longer
  blanked out — the last known figures stay on screen and the SCADA card turns
  them red so it is obvious they are stale rather than live. The affected
  sensors expose a `data_stale` attribute and `generation_source=stale`.
- **Retry failed summaries on a backoff schedule.** Timeframes that failed to
  fetch are retried sooner than the next hourly slow-tier slot, at escalating
  intervals (1, 2, 4, ... ticks capped at ~1 hour) so a transient API blip
  recovers quickly without hammering the endpoint, and each failure is logged
  as a warning with the scheduled retry tick.

## Version 4.8.71
- **Fix duplicate plotly charts on the History view.** Until now the plotly
  "Power & Wind (25h)" card stored its title inside `layout.title`, so the
  merge machinery could not match it and each restart left the old copy in
  place as a "user-added" card while appending a fresh one — duplicates
  compounded over time (13 copies were deployed). `_card_match_key` now falls
  back to `layout.title` for custom cards, so the merge replaces all legacy
  copies with the single managed card on the next reload.

## Version 4.8.70
- **SCADA card shows the running card version** in the bottom-left corner
  (e.g. `v4.8.70`). Because the card JS is cached by the browser, the badge
  makes it obvious when an old bundle is still loaded — if the shown version is
  behind the installed one, a hard refresh (Ctrl+Shift+R / clear cache / pull
  down in the companion app) is needed. `scripts/version_sync.py` keeps the
  badge version aligned with the rest of the release.

## Version 4.8.68 (stable)
- **SCADA card owner share now uses the authoritative sensor.** The SCADA card's
  "Share (‱)" readout used to derive the share from today's observed
  owner/site generation ratio, which could drift from the real figure by a large
  factor. It now prefers the capacity-derived
  `sensor.kirk_hill_wind_farm_owner_share` (the fixed share of watts bought) and
  only falls back to the observed-generation calculation if that entity is
  unavailable. Per-myriad (‱) display is unchanged, so the card now shows the
  true share (e.g. 1.36‱).
- The `dashboards/kirkhill_wind_scada.yaml` reference and the auto-built
  dashboard both receive the new `owner_share_entity` config.

## Version 4.8.67 (stable)
- **Fix: config-entry migration actually runs now.** The 4.8.66 migration
  handler was placed in `config_flow.py`, but Home Assistant looks up
  `async_migrate_entry` on the integration's `__init__.py` module (via
  `hasattr(component, "async_migrate_entry")`), not on the config flow. As a
  result the stored config entry stayed at version 3, the platforms never set
  up, and the new `owner_share` sensor and `number` entities from 4.8.66 never
  registered. The handler is now a module-level function in `__init__.py` and
  the version updates correctly to 4.
- No other user-facing changes in this release.

## Version 4.8.66 (stable)
- **Owner share now derived from the live API watt figures**: the owner share
  percentage is computed from the farm's `capacity_watts` ratio
  (`owner / site`). Since owner shares are watt-based, buying more watts raises
  the percentage automatically — no manual entry required, and the value is
  recomputed every poll instead of being cached forever.
- **New sensor**: `owner_share` (%) entity exposing the watt-derived share.
- **Removed redundant config fields**: `owner_share_percent` (now auto-derived)
  and the unused legacy `owner_value_rate` were dropped from the config and
  options flows. Existing entries are migrated automatically (config version 3
  → 4).
- **Editable projected-earnings figures**: the owner and site projected annual
  earnings (GBP) are now exposed as `number` entities on the integration. Users
  can adjust them live (values persist across restarts) instead of
  reconfiguring, e.g. when new share figures become available.
  - *Note: this release's auto-migration did not run (see 4.8.67); install
    4.8.67 instead, or it upgrades cleanly to it.*

## Version 4.8.65 (stable)
- **Resolve the farm hub device id once per setup**: `get_farm_device_id` is now
  called a single time in `__init__.py::async_setup_entry` (where the coordinator
  is created) instead of redundantly from both the sensor and binary_sensor
  platforms. No user-facing behavior change.
- **Code health**: removed dead local variables (`owner_value_entities`,
  `site_value_entities`, `kpi_cards`) and unused imports in `__init__.py`,
  `coordinator.py` and `sensor.py`, and wrapped an over-long string literal —
  this clears the ruff lint step in the HACS validation workflow. No runtime
  behavior change.
- All v4.8.64 features preserved.

## Version 4.8.64 (stable)
- **Deprecated `via_device` replacement**: turbine devices now link to the farm
  hub via the resolved hub device registry id (`via_device_id`) instead of the
  deprecated `via_device=(DOMAIN, entry.entry_id)` identifier tuple. Resolved
  once per setup via `get_farm_device_id(hass, entry)` and stored on the
  coordinator. Required for Home Assistant Core 2027.8 compatibility (needs a
  full HA restart for the Python `custom_components/` change to take effect).
- **Global chart timeframe control**: a "Chart timeframe" bar at the top of the
  SCADA card (6H / 12H / 24H / 1W / 1M / 6M / 1Y, 24H default). All modal charts
  (turbine, site, owner) now honour the selected range instead of a fixed 25h
  window. Range is stored per-card and headings show the active range.
- **Separate Site and Owner detail modals**: the Generation & Capacity panel now
  opens a dedicated detail modal for the selected scope (site or owner) with its
  own ApexCharts 25h-series charts, split from the single combined modal.
- All v4.8.63 features preserved.

## Version 4.8.63 (stable)
- **Hide default ApexCharts legend** in turbine modal charts (no duplicate legend).
- **Relabel per-turbine timestamp to "Status since"** so it is not mistaken for
  stale data — the value is the time the current status began.
- **Fix wind-panel text overflow**: title 16px, value 18px so content stays inside
  its box on the SCADA card.
- All v4.8.62 features preserved.

## Version 4.8.62 (stable)
- **Turbine Power and Wind Speed charts as line graphs** instead of area charts.
- **Fix blank modal charts**: ApexCharts and history are now loaded via
  `hassUrl`/`callApi` (`history/period`) so turbine modal charts render.
- **Simplify shipped dashboard**: collapse the redundant 25h chart stack in the
  Overview Charts section.
- All v4.8.61 features preserved.

## Version 4.8.61 (stable)
- **ApexCharts error handling**: turbine detail modal now shows a visible fallback message if ApexCharts fails to load (e.g., on iOS), instead of silently rendering empty chart placeholders. Load errors and timeouts are now logged to the browser console for diagnosis.
- All v4.8.60 features preserved.

## Version 4.8.60 (stable)
- **Fix status text color**: status text fill now uses `style.fill` instead of `setAttribute("fill", ...)` so CSS `var()` resolves correctly — text now shows the saturated status color (green/blue/red) against the pastel pill background.
- All v4.8.59 features preserved.

## Version 4.8.59 (stable)
- **Pastel status pills**: pill backgrounds now use `color-mix(in srgb, <status-color> 15%, card-bg)` instead of a solid saturated fill — gives a soft, muted pastel tint that works in both light and dark themes. Status text fill is set to the full status color via JS so it contrasts cleanly against the pastel pill.
- All v4.8.58 features preserved.

## Version 4.8.58 (stable)
- **Fix black-on-black theme rendering**: the card's `:host` color aliases referenced `--ha-*`-prefixed tokens (`--ha-card-background`, `--ha-primary-color`, `--ha-primary-text-color`, etc.) that do not exist in Home Assistant's global theme scope, and v4.8.54 removed the inline fallbacks — so backgrounds resolved transparent (showing the black page behind) and text fell back to black. Aliases now read HA's real theme tokens (`--card-background-color`/`--paper-card-background-color`, `--primary-text-color`, `--secondary-text-color`, `--primary-color`, `--success-color`, `--error-color`, `--warning-color`, `--divider-color`) with readable fallbacks, verified in both light and dark themes. All `color-mix()` background tints updated to the same real tokens.
- All v4.8.57 features preserved.

## Version 4.8.57 (stable)
- **Fix render crash on all engines (including iOS/WebKit)**: status pill no longer writes `className` on its SVG `<rect>` (a read-only `SVGAnimatedString` getter — a guaranteed `TypeError` in strict mode). The pill class is now applied via `setAttribute("class", ...)`, so the card renders instead of throwing.
- **Drop cyclic `--ha-font-size-*` tokens**: the self-referential `:host` definitions (e.g. `--ha-font-size: var(--ha-font-size, 14px)`) are guaranteed-invalid at computed-value time and silently broke font inheritance inside the Shadow DOM; they are removed so theme font tokens flow through normally.
- **Restore font fallbacks**: every `font:` shorthand using `var(--ha-font-size-*)` now carries an inline px fallback (12/14/16/18/20/24px) so a missing theme token cannot invalidate the whole rule.
- All v4.8.56 features preserved.

## Version 4.8.56 (stable)
- **Arrow marker theme-aware**: flow arrow now uses `--khscada-accent-color` (maps to `--ha-primary-color`) instead of hardcoded blue.
- All v4.8.55 features preserved.

## Version 4.8.55 (stable)
- **All backgrounds theme-aware**: turbine boxes, bus bar, National Grid box, chips, panels, alarm, legend — all use HA semantic color variables (`--ha-card-background`, `--ha-primary-color`, `--ha-success-color`, `--ha-error-color`) via local `--khscada-*` aliases with `color-mix()` for subtle tints. No hardcoded hex colors remain.
- Status pills & legend dots now use HA variables (success/accent/warn/error/disabled) instead of hex.
- All v4.8.54 features preserved.

## Version 4.8.54 (stable)
- **Full theme-aware SCADA card**: all fonts, colors, and styles now use HA CSS variables (`--ha-font-size-*`, `--ha-primary-text-color`, `--ha-secondary-text-color`, `--ha-card-background`, `--ha-divider-color`, `--ha-primary-color`, etc.) with local `--khscada-*` aliases. No hardcoded colors or absolute px remain. The card now fully responds to dashboard themes, font-size settings, and custom HA themes.
- All v4.8.53 features preserved.

## Version 4.8.53 (stable)
- **Shadow DOM fix for HA font tokens**: added `:host` variable inheritance so `--ha-font-size-*` tokens now penetrate the card's Shadow DOM. Generation panels, turbine nodes, and all text now respond to HA's global font-size setting.
- All v4.8.52 features preserved.

## Version 4.8.52 (stable)
- **Full SCADA card uses HA native font tokens**: every text element now references `--ha-font-size-*` variables (small/large/xlarge/xxlarge/xxxlarge) instead of absolute px. The card now scales with the user's HA font-size setting and matches system hierarchy.
- Turbine nodes, transformer, chips, panels, alarm, legend, and modal all converted.
- All v4.8.51 features preserved.

## Version 4.8.51 (stable)
- **National Grid box uses HA native font tokens**: labels/units → `--ha-font-size-large` (16px), title/values → `--ha-font-size-xxlarge` (20px bold). Now scales with user's HA font-size setting and matches system hierarchy.
- All v4.8.50 features preserved.

## Version 4.8.50 (stable)
- **National Grid box fonts softened**: labels and units raised to 16px, values lowered to 20px bold (was 13/23), reducing the label/value size gap from 10px to 4px for a more balanced look. Title stays 20px bold.
- All v4.8.49 features preserved.

## Version 4.8.49 (stable)
- **National Grid box fonts aligned to the card-wide scale**: the box previously rendered every element at 22px (title, labels, values, units) — the only element that broke the size hierarchy. Title now bold 20px, labels 13px, values bold 23px and the "kWh" unit 13px, matching the Owner/Site/Wind panels exactly. Dead `.grid-col` rule removed.
- All v4.8.48 features preserved.

## Version 4.8.48 (stable)
- **Fix turbine detail modal charts showing no data**: the modal depends on ApexCharts, which was never loaded, so `_renderCharts` silently returned and every chart stayed empty. ApexCharts (v4.4.0) is now bundled with the integration and lazy-loaded the first time the modal opens.
- **"Active Turbines" pill compacted**: width 190 → 150, label 13px → 12px and value 14px → 13px so it no longer dominates the header row.
- **Re-center button now level with the legend**: the status legend's two lines are vertically centred in their block, matching the button's height.
- **National Grid box narrowed**: width 265 → 225 (right edge now at x1200 instead of the card edge). The Owner/Site panels re-align to the grid box's new right edge so the right column still lines up.

## Version 4.8.47 (stable)
- **Turbine staircase collapse**: the gap between the two turbine columns starts smaller (40 instead of 70). As the card narrows, the right-hand column now slides under the left one until it merges into a single column.
- **Gap between merged turbine boxes**: stacked boxes gain a small vertical gap as the columns merge, so they never touch once in single-column mode. Box height budget absorbs the gap so the block still clears the National Grid box.

## Version 4.8.46 (stable)
- **Re-center button moved out of the top-right corner**: now sits at the bottom-left, immediately left of the status legend and vertically centred against it (height matches the legend's two lines).
- **National Grid box now lines up with the Generation & Capacity panels**: the Owner and Site panels extend to the card's right edge (same right edge as the National Grid box), so the right-hand column aligns. Value columns moved to keep the same right padding.

## Version 4.8.45 (stable)
- **Fix Wind & Forecast panel overlap**: the panel now ends 8px before the National Grid bus line, so it no longer overlaps the transformer/bus bar.
- **Fix "Active Turbines" pill text overlap**: pill widened with label left-aligned and the "8 of 8" count right-aligned, so the label no longer collides with the value.
- **Fix turbine status pill overflow**: pill widened so longer statuses (e.g. `THERMAL FAULT`, `MAINTENANCE`, `UNAVAILABLE`) no longer spill outside the pill at narrower card widths.
- All v4.8.44 layout fixes preserved.

## Version 4.8.44 (pre-release)
- **Fix overlapping layout elements**: viewBox minimum height restored to 1052 (was incorrectly lowered to 860 in v4.8.42). At 860 the National Grid box (top at `H−460`) collided with the Site Generation & Capacity panel, and the status legend (`H−150`) overlapped the bottom turbines (T7/T8). With `hMin: 1052` the grid box sits below the panels and the legend clears the turbine block again.
- Card still bounded to the viewport (`calc(100vh - 64px)`) — the v4.8.43 fix is unchanged.

## Version 4.8.43 (stable)
- **SCADA card no longer inflates past the screen**: restores viewport-bounded sizing — `ha-card` capped at `calc(100vh - 64px)` with `:host` filling the grid cell, so the card always fits on-screen regardless of grid size. The v4.8.41 change to `height: 100%` let the grid inflate the card beyond the viewport; reverted to the v4.8.38 approach.
- All v4.8.40 features preserved: turbine detail modal, generation timeframes, mouse/pinch zoom, reset button, theme-aware ApexCharts.

## Version 4.8.42 (stable)
- **Fix vertical stretch**: VIEWBOX `hMin` changed 1052 → 860 (matches design height), `hMax` 1600 → 1200 (limits expansion).
- ResizeObserver derives the viewBox from the actual container aspect ratio.
- HA grid sizing via `getCardSize()`/`getGridOptions()`.
- All v4.8.40 features preserved.

## Version 4.8.40 (stable)
- **Turbine detail modal** with historical charts (Power, Wind vs Power, Capacity Factor, Rotor Speed, Wind Speed, Generation Today) — tap a turbine to open.
- **Generation & Capacity panels** with timeframe breakdowns (Yesterday, Today, Week, Month, YTD, Year, All time) for Owner and Site.
- **Wind & Forecast panel**.
- **Mouse wheel zoom + drag pan** for browser displays; pinch zoom + drag pan for touch devices.
- **Double-click / double-tap to reset zoom** and a reset zoom button (⟲).
- **Theme-aware ApexCharts** coloring.
- **Fixed**: removed forced heights that broke dashboard layouts — card uses HA grid sizing via `getCardSize()`/`getGridOptions()`. Supersedes the retracted v4.8.39 / v4.8.41–43 experiments.

## Version 4.8.38 (stable)
- **Wind panel moved left**, National Grid simplified, turbine ID/status aligned.

## Version 4.8.37 (pre-release)
- **Flow-dot speed proportional to line length + power**: energy-flow dots animate faster with higher power output, scaled by feed-line length.

## Version 4.8.36 (stable)
- **Fix SCADA card temporal-dead-zone crash**: `gridRectX` was read before its `const` declaration (introduced in v4.8.35.1), throwing `ReferenceError` and leaving the dashboard in a "configuration error" state.
- **Dashboard entity mapping fixes**: wind forecast → `open_meteo_next_hour_wind_speed_mps`, capacity factor scoped to site/owner entities, `async_load(False)`.
- Includes all v4.8.35.1 / v4.8.35.2 / v4.8.35.4 fixes.

## Version 4.8.35.4 (pre-release)
- **Fix dashboard creation race**: `_async_ensure_dashboard` re-fetches the dashboard item on `url_already_exists` (concurrent setup calls) and continues with merge/save instead of silently returning.
- **Empty turbines guard**: `_build_dashboard_config` falls back to T1–T8 with a debug log if no turbine entities are registered yet, preventing the SCADA card `setConfig()` from throwing.
- **Remove hardcoded entity IDs**: SCADA card config now uses `farm()`/`farm_scoped()` lookups for wind speed, wind forecast, active, alarm, and capacity factors — works with any site name and avoids `_2` suffix collisions.
- Includes all v4.8.35.2 / v4.8.35.1 fixes.

## Version 4.8.35.2 (pre-release)
- **Fix silent dashboard overwrite**: `_async_ensure_dashboard` logs a warning when loading the existing dashboard config fails, instead of silently overwriting user customizations with defaults.
- **Guard summary access in sensors**: farm active/inactive sensors use defensive `.get()` chains so a malformed/missing `summary` returns `unavailable` instead of raising `KeyError`.
- **Deduplicate `_owner_share_pct()`**: moved from `FarmPowerSensor` and `FarmGenerationByTimeframeSensor` to the shared `KirkHillScopedEntity` base class in `entity.py`.
- Includes all v4.8.35.1 changes.

## Version 4.8.35.1 (pre-release)
- **Font size increases** across all dashboard elements for readability: SCADA turbine details (11→14px), panels (17→20px), grid titles/values (20→22px), chips (11→14px), alarm (12→13px), turbine map labels (11→13px).
- Includes all v4.8.35 changes.

## Version 4.8.35 (pre-release)
- **Fully responsive SCADA card**: diagram now scales proportionally in both width and height to fit any container (mobile, panel view, side-by-side). ViewBox bounds 900–1800w × 1052–1600h. All coordinates derived from design width (1240) so layout stays intact at any size.
- **Flow arrow to grid box center**: energy-to-grid flow line and animated dot now terminate at the center of the National Grid box (halfway up) instead of the left edge.
- **Text/formatting polish**: Owner panel → "Capacity Factor (%)", "Your Share (W)", "Owner Capacity Factor (%)", "Share (‱)"; Site panel → "Site Capacity Factor (%)", "Site Power (MW)"; Wind panel → "Wind & Forecast", "Current Wind", "Forecast (1h)"; Grid → "To Grid Today". Finances tab headings title-cased. Turbine map legend spacing improved.
- **Bug fix**: `sitePowerText` reassignment changed from `const` to `let` (prevented card render in strict mode).

## Version 4.8.34 (pre-release)
- **Turbine staircase layout**: turbines now form a brick-wall staircase — T1 left, T2 right with its top level with T1's bottom, T3 left level with T2's bottom, and so on — so every feed line reaches the bus unobstructed. The block is spread to roughly match the bus bar height, and boxes are sized taller to leave room for more per-turbine details.

## Version 4.8.33 (pre-release)
- **Generation & capacity panel**: the top-right "Your generation" box is now "Generation & capacity" with separate lines for Generation (today), Percentage (owner capacity factor), Your share (live watts), Capacity (site capacity factor) and Share % (observed % of site generation today).
- **Wind & forecast panel**: wind speed and next-hour forecast now live in their own box directly below Generation & capacity (site capacity moved up into the panel above).

## Version 4.8.32 (pre-release)
- **Turbines staggered**: turbines are now arranged in two staggered columns (even on the left, odd on the right) instead of one tall column, so the turbine block fits in a much smaller top-to-bottom section.
- **Transformer label on the bus**: "TRANSFORMER" and "33 kV" now sit directly on the site collection bus bar (bigger, bold) instead of floating beside it.

## Version 4.8.31 (pre-release)
- **Simpler single-line diagram**: the separate transformer box is removed — "TRANSFORMER" now reads vertically down the site collection bus with a "33 kV" label, and the top "SITE COLLECTION BUS" wording is dropped. The National Grid box is moved up so its bottom edge lines up exactly with the bottom of the site collection bus, and the flow line enters the grid box there.

## Version 4.8.30 (pre-release)
- **Light theme**: the SCADA card now uses a light background (slate-100 shell, white panels) with dark slate text and slightly deeper accent colours (sky/blue bus, green grid, status pills unchanged), replacing the near-black navy background that was hard to read. Flow dots, arrows and hover highlights use a darker sky blue that stands out on light.

## Version 4.8.29 (pre-release)
- **Fix farm generation counters stuck on stale values**: the farm "generation today / yesterday / week / month / year / all-time" sensors were permanently frozen at the value restored on startup — the restored value took priority over live API data forever, so e.g. "Generation today" stopped updating after the first restart and showed yesterday's total. Live API data now takes priority, with the restored value used only as a placeholder until the first fetch after startup.

## Version 4.8.28 (pre-release)
- **Transformer and National Grid moved to the bottom**: the single-line diagram now reads turbines → bus → transformer → grid flowing down the card, with the transformer and National Grid box at the bottom (below the turbine stack) instead of the vertical centre

## Version 4.8.27 (pre-release)
- **Wind section uniform text**: "Current wind", "Forecast 1h" and "Site capacity" moved out of the small 11px chips into a proper "Wind & capacity" panel below "Your generation", now matching the same 20px size as the rest of the right-hand text

## Version 4.8.26 (pre-release)
- **Fix state class warning**: turbine "Generation today" sensors now use `state_class: total` (with `device_class: energy`) instead of `measurement`, matching the farm-level today sensor and Home Assistant's validation, so the "state class 'measurement' is impossible considering device class 'energy'" warnings are gone

## Version 4.8.25 (pre-release)
- **Uniform right-side text**: every label, value and unit in the National Grid box and the "Your Generation" panel now uses a single 20px size (bold for values/titles) instead of the previous mix of 11–27px, so the right-hand figures read as one consistent block

## Version 4.8.24 (pre-release)
- **Bigger right-side text**: National Grid box labels, values and units enlarged (title 16→20px, values 20–22→24–27px, labels/units 11→14px) and the top-right "Your Generation" panel enlarged, so both stay readable when the card is scaled down on phones
- **Owner export auto-derived**: when the API reports no owner power (owner share is tiny), the National Grid "Export" row now shows the owner export computed as site export × owner's share of today's generation (in W), instead of "—"; the "Your share" line uses the same value
- National Grid box now shows per-column units (owner export in W, site export in MW) and the "Export (MW)" row label is just "Export"

## Version 4.8.23 (pre-release)
- **National Grid "To grid today" figures fixed**: the SCADA card config was wired to the owner generation entity for both Owner and Site, so Site showed the owner's value (and Owner + Site looked identical). Site now resolves to the site generation entity via the entity registry (all other dashboard cards already did this; the SCADA card now matches).
- **Your share panel**: owner export power is now reported in watts (was mislabelled kW as W, off by 1000×, and rounded small values to "0 W")
- SCADA card now replaces (not duplicates) its stored copy on dashboard merge

## Version 4.8.22 (stable)
- **Turbine map mobile parity**: double-tap to reset the map view (matches the SCADA card, previously double-click only); legend hint updated to "Double-tap to reset"

## Version 4.8.21 (stable)
- **Mobile pinch-zoom and pan on the SCADA card**: two-finger pinch to zoom (up to 6x), one-finger drag to pan, double-tap to reset, `touch-action: none` so the browser does not hijack gestures
- Turbine tap still opens more-info on touch devices

## Version 4.8.20 (stable)
- **"Your Generation" panel moved to the far right** of the SCADA card (after the wind/forecast/capacity chips)

## Version 4.8.19 (stable)
- **SCADA entity IDs fixed**: use actual registry IDs (fixes missing data)
- **SCADA title removed** (saves space)
- **Your Generation panel** (top right): your generation (auto-scaled), last updated, your share in watts
- **Owner capacity factor** and **owner today generation** entities added to SCADA
- **Owner power fallback**: calculates from site power × owner share % when API returns 0/None

## Version 4.8.18 (stable)
- **Owner power fallback**: Calculates from site power × owner share % when API returns 0/None
- **SCADA "Your Generation" panel** (top right): your generation (auto-scaled), last updated timestamp, your share in watts
- **Owner capacity factor** and **owner today generation** entities added to SCADA

## Version 4.8.17 (stable)
- **Optimized API fetch tiers**: "yesterday" moved to slow tier (hourly) since it's static once the day ends; removed medium tier (week/month now also hourly); only "today" fetches every poll
- Reduces unnecessary API calls — yesterday/week/month/ytd/year/alltime now only fetch hourly

## Version 4.8.16 (stable)
- **State restoration for generation sensors**: farm and turbine generation sensors now restore their last known values on Home Assistant restart, avoiding "—" gaps while waiting for slow-tier API fetches
- Added `RestoreEntity` to `FarmGenerationByTimeframeSensor`, `TurbineGenerationTodaySensor`, `TurbineGenerationAlltimeSensor`

## Version 4.8.15 (stable)
- **Overview tab removed**: dashboard now starts with SCADA, then Finances, History, Turbines
- **Finances tab moved to second position** (after SCADA)
- **Obsolete view cleanup**: Overview view automatically removed from existing dashboards on merge

## Version 4.8.14 (stable)
- **Overview cleanup**: removed KPI row (Alarm tile, Reload button) and Site metrics card; Overview now shows only Owner/Site generation markdown cards
- **Finances tab fixed**: now shows generation kWh alongside projected earnings for all timeframes (Owner & Site), not just monetary values
- **Obsolete card/section cleanup**: removed cards/sections automatically pruned on dashboard merge

## Version 4.8.13 (stable)
- **SCADA dashboard redesign**: alarm + active turbines moved above turbine list (left), always-visible alarm chip (OK / flashing ALARM), cleaner National Grid box, renamed wind chips (Current Wind / Forecast 1h), new Site Capacity chip
- **Capacity Factor moved**: removed from Overview KPI row and Site metrics; added to SCADA dashboard as "Site Capacity"
- **Bus summary removed** (redundant with National Grid box)
- **Turbine status legend moved** to left side below turbine list
- **Dashboard customisation preserved** with factory reset options documented
