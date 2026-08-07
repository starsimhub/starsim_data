# Migrating laser-init capabilities into starsim_data

An assessment of [`laser-init`](https://github.com/laser-base/laser-init) against this package, identifying what to port, what to leave behind, and where the two overlap. Written against `laser-init` at commit `6d04235` and `starsim_data` at `c51fe3b`.

**Scope note on spatial.** Starsim has essentially no spatial machinery today — `ss.MixingPools` is age/group-structured, not geographic, and `location=` is not yet a `Sim` parameter. Spatial support *is* planned. Almost everything `laser-init` does is spatial, so the fact that starsim_data cannot use those pieces *yet* is not a reason to drop them. This document treats spatial capability as the single most valuable thing to preserve, and proposes a data layout that leaves room for it rather than one that has to be rebuilt when spatial lands.

---

## 1. The two packages at a glance

| | `starsim_data` | `laser-init` |
|---|---|---|
| **Model** | Bundle curated data in the wheel | Download from upstream at runtime, cache locally |
| **Interface** | Library: `load()`, `list_datasets()`, `list_locations()` | CLI: `laser-init NGA 2 2000 2025` |
| **Runtime code** | ~200 lines (`starsim_data/loaders.py`) | ~4,500 lines across 28 modules |
| **Build tooling** | ~470 lines (`scripts/`, dev-only, not shipped) | n/a — everything happens at runtime |
| **Tests** | ~240 lines | ~4,100 lines, 90% coverage gate |
| **Runtime deps** | 3 (`numpy`, `sciris`, `h5py`) | 15 (incl. `geopandas`, `pyogrio`, `rastertoolkit`, `matplotlib`, `click`, `openai`, `anthropic`) |
| **Network at runtime** | Never | Always (on cache miss) |
| **Geography** | Level 0 (country) only, no geometry | Levels 0–4, full geometry + gridded population |
| **Demographics** | UN WPP 2024, decadal 1950–2100, 187 countries | UN WPP 2024, annual, any country/range |
| **Contact matrices** | prem2017 / prem2021 / mistry2021 | none |
| **Output** | `sciris.dataframe`, Starsim-native column names | CSV + GeoPackage + a runnable model script + PDF report |
| **Data size** | ~13 MB bundled | 1–2 GB cache for the default shape source alone |
| **Licensing** | `NOTICE.md`, `licenses/`, per-source attribution | `LICENSE` (MIT) only |
| **Reproducibility** | Pinning the package version pins the data byte-for-byte | Output depends on when you ran it |
| **CI / lint / changelog** | none | `ci.yml`, `docs.yml`, ruff, `CHANGELOG.md` |

The packages are close to complements rather than competitors: `starsim_data` is a *distribution* problem solved well, `laser-init` is an *acquisition* problem solved well. The interesting question is not "which wins" but "where does the seam between them go."

---

## 2. The central design question: bundle vs. fetch

`starsim_data`'s defining property is that `pip install starsim_data==0.1.0` gives every user byte-identical data with no network access. That buys offline use, deterministic tests, and citable reproducibility. It works because the data is small: four HDF5 stores totalling ~13 MB cover 187 countries of demographics and 177 countries of contact matrices.

That property does not survive contact with spatial data. UNOCHA's global boundary geodatabase is 1–2 GB. A single WorldPop country-year raster is 10–200 MB. Admin-2 geometry for one large country is tens of MB. Bundling is not an option at that scale, so **the spatial tier has to be fetch-and-cache — which is exactly the machinery `laser-init` already has.** This is the strongest argument for porting `laser-init`'s extractor/cache/provenance layer: not to replace the bundled demographics, where bundling clearly wins, but to enable the tier where bundling is impossible.

The recommendation is therefore a **tiered data model**, with the tier boundary drawn by size rather than by subject:

- **Tier 0 — bundled in the wheel.** National demographics, contact matrices, `locations.csv`. Today's behaviour, unchanged. Reached via `ssd.load()`. No network, ever.
- **Tier 1 — release assets, downloaded once, cached.** Things too big for the wheel but small enough to fetch in seconds and version alongside a release: subnational demographics, and (see §5.3) a **node table** of admin-0/1 centroids, areas and populations. Reached via `ssd.load()` with a transparent one-time download.
- **Tier 2 — fetched from upstream on demand, cached, provenance-tracked.** Admin-N boundaries, population rasters, raster→admin aggregation. This is `laser-init`'s pipeline, ported behind an optional extra. Reached via an explicitly different verb (`ssd.fetch()`), because the cost and the reproducibility characteristics are different and the API should say so.

Keeping tiers 1 and 2 behind a *different function name* than `load()` is deliberate: it preserves the "`load()` never touches the network" invariant that makes the current package trustworthy, while making the escape hatch discoverable.

---

## 3. Overlapping functionality

### 3.1 UN WPP demographics — both packages do this

Both extract from UN WPP 2024 Medium variant. They differ in *when*.

`starsim_data` (`scripts/download_wpp.py`, `scripts/build_demographics.py`) hits the WPP Data Portal API at build time for four indicators (CBR 55, CNMR 66, mx 79, population 46), filters to decadal years and this package's countries, and freezes the result into `demographics-<revision>.h5`. `laser-init` (`extractors/unwpp.py`, `transformers/unwpp.py`) downloads the bulk gzipped CSVs at runtime and filters them per invocation.

| | `starsim_data` (pre-baked) | `laser-init` (runtime fetch) |
|---|---|---|
| **Pros** | Instant; offline; deterministic; 3 MB not 200 MB; version-pinned data; already emits Starsim-native columns | Any year 1950–2100 at annual resolution; complete single-age life tables (`lx`, `qx`, `ex`, …); always the current revision; trivially extended to other variants |
| **Cons** | Decadal snapshots only; frozen at WPP2024 Medium; no life tables; 187 countries; new indicators need a rebuild + release | Slow first run; needs network; ~50–200 MB downloads; output depends on run date; no attribution/NOTICE machinery |

**Recommendation: keep the bundled path as the default, port the fetch path as the gap-filler.** The gaps are real and named in the current README — annual resolution, life tables, non-Median variants — and the fetch path closes all three without disturbing tier 0. Concretely, `laser-init`'s `UnwppExtractor` is worth porting largely as-is (it is 136 straightforward lines) into a tier-2 `ssd.fetch('kenya', which='deaths', years=(2000, 2025))`, while the *transformer* is not: its output schema (`cxr.csv`, `age_dist.csv`, `life_exp.csv` with a `cumulative_deaths` column) is shaped for `laser.generic`'s `KaplanMeierEstimator` and `AliasedDistribution`, not for Starsim. Reuse the extraction and filtering logic; keep this package's tidy `[Time, Sex, AgeGrpStart, mx]` output shape.

*Verified compatibility note while assessing this:* `ss.Deaths(death_rate=ssd.load('kenya', which='deaths'))` works unmodified, but `ss.Births(birth_rate=ssd.load('kenya', which='births'))` raises `KeyError: 'Year'` — `ss.Births`'s default metadata expects a `Year` column and this package emits `Time`. It works with `metadata=dict(data_cols=dict(year='Time', value='CBR'))`. Worth resolving on one side or the other before advertising drop-in compatibility in the README.

### 3.2 Country/location resolution — both packages do this, `laser-init` does it much better

`starsim_data._match_location` (`starsim_data/loaders.py:44`) normalizes by `strip().lower().replace(" ", "_")` and requires an exact match against the stored keys. `laser-init.iso_from_country_string` (`src/laser/init/utils.py:92`) does Unicode NFKD decomposition, strips combining marks, casefolds, and matches against ISO-3 codes, `pycountry` names, `pycountry` official names, a ~250-entry French name table (`french_iso.py`), and a hand-curated short-name table (`congo`, `iran`, `tanzania`, …). On a miss it runs `pycountry.countries.search_fuzzy` and *warns with candidates rather than guessing* — a good failure mode.

| | `starsim_data` | `laser-init` |
|---|---|---|
| **Pros** | Zero dependencies; deterministic; ~10 lines; no chance of silently resolving to the wrong country | Handles `USA`, `Côte d'Ivoire`, `Viet Nam`, `République démocratique du Congo`, accented and French input; suggests candidates on a miss |
| **Cons** | `'USA'`, `'DRC'`, `'Côte d'Ivoire'`, `'Viet Nam'` all fail against stored keys | Pulls in `pycountry` + `rapidfuzz`; fuzzy suggestions are advisory and could mislead if ever made automatic |

**Recommendation: port this, first, but reimplement the machinery on sciris.** It is the highest value-per-line item in the whole assessment: small, self-contained, no spatial prerequisites, and it fixes a real usability cliff (`ssd.load('USA')` currently raises). Port `_normalize_string`, the alias tables and the French mapping into a `starsim_data/locations.py`.

What should *not* be ported is the dependency stack underneath. `sc.suggest(user_input, valid_inputs, n=..., threshold=..., die=True)` does exactly what `rapidfuzz` + `pycountry.search_fuzzy` were doing in `laser-init`, defaults to Damerau-Levenshtein (the algorithm `laser-init/utils.py:6` says it chose), and `die=True` raises an informative error listing candidates — the warn-with-candidates failure mode, already implemented. And `pycountry`'s value here is a static table, so **generate it at build time into `locations.csv`** (add `iso3`, `official_name`, and an `aliases` column) and make `pycountry` a dev-only dependency of the build scripts. That gives the full matching behaviour with **zero new runtime dependencies** and settles the `pycountry` question outright (§3.8).

The division of labour matters, and a quick check against the real location list makes it concrete: `sc.suggest` handles typos and spacing well (`'Keyna'` → `Kenya`, `'Viet Nam'` → `Vietnam`, `'Cote dIvoire'` → `Cote_dIvoire`), but returns `None` for `'USA'` — abbreviations are below its edit-distance threshold and always will be. So **the alias table resolves, `sc.suggest` only advises.** Codes, abbreviations and alternate names go in the generated table and match exactly; fuzzy matching runs solely on the miss path, to build the "did you mean" message. Note also that `sc.suggest` will happily offer candidates for genuinely absent input (`'Atlantis'` → `Albania, Algeria, Armenia`), which is fine in an error message and would be actively harmful if it ever fed resolution.

`locations.csv` already has `iso_code`/ISO-2 and, notably, a `level` column that is all-zero today — the right seam for subnational keys later. Do **not** port the LLM resolution path (§6).

Also port `level_from_string` (`utils.py:147`, parses `admin1` / `ADM2` / `3` → `int`). It is trivial and it is the vocabulary the spatial tier will need.

### 3.3 Provenance — `laser-init` has it, `starsim_data` does not

`laser-init` writes two `provenance.json` files: one in the cache recording source URL and download timestamp per file (`utils.py:257`), and one in the output directory recording which cached inputs produced each output (`utils.py:285`). `starsim_data` has no runtime provenance; the equivalent information lives in prose in `NOTICE.md` and the folder READMEs, plus a `spec` JSON attribute on each HDF5 group describing layout only.

| | `starsim_data` | `laser-init` |
|---|---|---|
| **Pros** | Attribution is thorough, human-readable and legally careful; `spec` makes the stores self-describing for layout | Machine-readable; per-file lineage; survives being handed a bare output directory |
| **Cons** | Nothing machine-readable ties a returned dataframe to its source URL, WPP revision or build date | Prose attribution and licensing are absent entirely; JSON lives next to the data and is easily separated from it |

**Recommendation: port the concept, not the code, and improve on it.** Write provenance *into* the HDF5 `spec` at build time — source URL, download timestamp, upstream revision (e.g. "WPP 2024 Medium"), builder git SHA, license identifier — and expose it as `ssd.provenance(which)` and/or on the returned frame's `.attrs`. That is strictly better than `laser-init`'s sidecar JSON because it cannot be separated from the data, and it costs almost nothing: the `spec` mechanism already exists (`scripts/build_demographics.py:109`, `scripts/build_hdf5.py:99`). For tier 2, the sidecar-JSON approach is the right one and should be ported closer to as-written, since fetched files are ordinary cache entries.

### 3.4 Configuration and logging — `laser-init` has both, and both are cautionary

`laser-init` loads `laser_config.yaml`/`.json` from the CWD or `~/.laser/` at import time into a module-level `configuration` dict (`config.py`), and configures a dual-handler logger at import time that creates `~/.laser/logs/` and opens a new timestamped log file (`logger.py`).

**Recommendation: mostly do not port.** These are CLI ergonomics implemented as import-time side effects, which is a liability in a library. Specific things to avoid carrying over: `config.py:150` emits a `UserWarning` on *every import* when no config file exists; `logger.py:114` creates a directory and opens a file handle merely because a module was imported; a mutable module-level `configuration` dict read directly by extractors makes them untestable without `importlib.reload` (which is exactly what `tests/conftest.py` has to do).

What *is* worth taking is the underlying need: tiers 1–2 need a cache directory and it needs to be user-overridable. Do that with a lazily-read setting (env var, or a `sc.options`-style object matching Starsim's conventions) resolved at call time, not at import time. Default to a platform-appropriate cache dir. No logging config at all — a library should get a `logging.getLogger(__name__)` and leave handler configuration to the application. `pyyaml`, incidentally, is not needed either: sciris already carries it, and nothing here requires a YAML config file in the first place.

### 3.5 Registry and Protocol interfaces — `laser-init`'s best architectural idea

`laser-init/interfaces.py` declares six `runtime_checkable` Protocols (`ShapeExtractor`, `RasterExtractor`, `StatsExtractor`, `ShapeTransformer`, `StatsTransformer`, `ModelLoader`) and `registry.py` maps CLI names to implementations through frozen dataclasses that keep each extractor paired with its transformer. Adding a source is one module plus one registry entry. The module docstring's justification for Protocols over ABCs — the roles genuinely differ in signature, so no single hierarchy fits — is sound.

`starsim_data`'s equivalent is `load()` dispatching on `spec["layout"]` through an if-chain (`loaders.py:150–168`) with dataset discovery by filename glob (`list_datasets`). That is proportionate for two layouts and 200 lines. It will not survive a third data family.

**Recommendation: port the pattern, not the taxonomy, and do it before the spatial tier lands rather than after.** A `DATASETS` registry mapping name → descriptor (layout, loader callable, tier, level, license, provenance, list of available locations) replaces both the layout if-chain and the filename-glob discovery, and gives `list_datasets()` something richer to return. What should *not* be ported is the extractor/transformer/loader trichotomy wholesale: `starsim_data` has no "loader" phase (§6) and for tier 0 has no extract phase at runtime either. Two roles — *fetch* and *shape* — is the right factoring here.

Worth noting from `laser-init`'s own `misc/integration-plan.md`: their registry is module-level dict literals with no public `register_*`, and their pipeline lives inside `cli.py`, both of which they identify as blockers to downstream reuse. Build the registry with a public registration hook and keep the pipeline in library functions — the mistake is already documented, so it is free to avoid. (There is no CLI here to wrap; see §9.8.)

### 3.6 Plotting and validation — `laser-init` has it, `starsim_data` does not

`laser-init/cli.py:447–722` generates a population choropleth, a CBR/CDR time series, an age pyramid and a Kaplan-Meier survival curve, and combines them into `report.pdf`. These are validation artefacts: they are how you notice you got the wrong country or the wrong units.

**Recommendation: port a small subset, no extra needed.** An `ssd.plot(location, which)` covering the age pyramid, the rate time series and a contact-matrix heatmap (and, later, the choropleth) is cheap and genuinely useful for data QA — the value is in catching a silent unit or country error before it reaches a simulation. `matplotlib` arrives transitively through sciris and is a direct Starsim dependency, so there is no reason to hide this behind an optional extra (§3.8). Do *not* port the `PdfPages` report assembly; that is a CLI-workflow artefact, not a library feature. Note also that `laser-init`'s age-pyramid plot fakes the sex split by duplicating `PopTotal` (`cli.py:621`) — this package has real per-sex data and should not reproduce that shortcut.

### 3.7 Packaging, CI, docs

`laser-init` has `ci.yml` and `docs.yml`, a ruff config (line length 100, `E,W,F,I,B,C4,UP`), a pytest config with markers and a 90% coverage gate, a `CHANGELOG.md`, and a mkdocs/mkdocstrings site. `starsim_data` has none of these — no `.github/`, no changelog, no lint config.

**Recommendation: port the scaffolding selectively; don't inherit `laser-init`'s toolchain along with it.** The pytest markers (`network`, `slow`, and `integration` become genuinely load-bearing once tier 2 exists), the coverage gate and the changelog are cheap and should just be adopted. Two things to leave behind. The docs site should **not** be mkdocs. *Decided on review: the site is built with [great-docs](https://posit-dev.github.io/great-docs/), which renders Quarto and additionally generates the API reference from docstrings.* And **no lint config at all** — not `laser-init`'s ruff, and not Starsim's `.flake8`/`pylint` either. A package this size does not have a style-drift problem worth a CI gate, and a satellite repo that imposes its own lint policy just creates friction at review time. **Decided on review: dropped.** Port the *content* patterns from `laser-init` instead — `docs/datasources.md` in particular (§5.6).

### 3.8 Dependencies — most of `laser-init`'s stack is already in sciris

This started as a check on the "3-dependency floor" and turned into the most consequential finding in the assessment, so it gets its own section. `sciris` — already a required dependency of this package — transitively provides `matplotlib`, `tqdm`, `pyyaml`, `zstandard`, `jellyfish`, `pandas` and `python-dateutil`, and ships utilities that cover most of what `laser-init` pulled third-party libraries in to do:

| `laser-init` dependency | Used for | `starsim_data` equivalent | New dep? |
|---|---|---|---|
| `requests` + `tqdm` | `download_file` (`utils.py:193`): streaming download, progress bar, cache check | `sc.download()` / `sc.urlopen()` — and `sc.download` parallelizes, which `laser-init` does not | none |
| `rapidfuzz` + `pycountry.search_fuzzy` | fuzzy country matching, candidate suggestions | `sc.suggest()` — Damerau-Levenshtein by default, `die=True` raises with candidates | none |
| `pycountry` | static ISO-3/name/official-name tables | bake into `locations.csv` at build time (§3.2) | dev-only |
| `pyyaml` | config file parsing | not needed (§3.4); sciris carries it anyway | none |
| `zstandard` | decompressing UNOCHA `.gpkg.zstd` | sciris dependency | none |
| `matplotlib` | validation plots | sciris dependency; also a direct Starsim dependency | none |
| `click` | CLI | not ported -- no CLI (§9.8) | none |
| `openai`, `anthropic` | LLM country resolution | not ported (§6) | none |
| `geopandas`, `pyogrio` | boundary I/O | no equivalent | **yes — `[spatial]`** |
| `rastertoolkit` | raster → admin aggregation | no equivalent | **yes — `[spatial]`** |
| `laser-generic` | the emitted model scripts | not ported (§6) | none |

So the entire P0/P1 programme — location resolution, cached downloads, on-demand WPP fetch, validation plots — can be built with **no new runtime dependencies at all**, and the only genuinely new ones in the whole plan are the three spatial libraries. That is a much better position than the original framing assumed, and it removes the main argument for splitting the spatial tier into a separate package (§9).

The practical implication for the port is to *reimplement against sciris rather than translate*. `laser-init`'s `download_file` is 62 lines of `requests` streaming, chunking, tqdm bookkeeping and provenance; the sciris version is `sc.download()` plus roughly fifteen lines of cache-hit check and provenance write. Copying the original would import a dependency and a hundred lines to reproduce behaviour that already exists.

---

## 4. Where the packages disagree on output schema

Both packages transform the same WPP inputs, and both invent a target schema — but for different simulators. `laser-init` emits `cxr.csv` (`Time`, `CBR`, `CDR`), `age_dist.csv` (`AgeGrpStart`, `PopTotal`) and `life_exp.csv` (`cumulative_deaths`), shaped for `laser.generic`'s `BirthsByCBR`, `AliasedDistribution` and `KaplanMeierEstimator`. `starsim_data` emits tidy frames with UN-native column names that feed `ss.Deaths` directly.

There is nothing to reconcile here and no reason to try: **port extraction logic, never output schemas.** The one thing worth borrowing is the *discipline* — `laser-init` documents the WPP life-table column semantics inline (`transformers/unwpp.py:124–134`, the `mx`/`qx`/`lx`/`Lx`/`Sx`/`Tx`/`ex`/`ax` glossary), which is exactly the kind of note that prevents a units error two years later. If life tables get ported, port that comment with them.

---

## 5. Spatial: what to preserve

None of this has a `starsim_data` counterpart, and none of it is usable until Starsim grows spatial support. It is also the part that is expensive to rebuild from scratch, so it is the part most worth capturing now — at minimum as a documented design, ideally as code behind a `[spatial]` extra.

### 5.1 Administrative boundary sources

Three interchangeable shape sources, each with an extractor/transformer pair: **UNOCHA COD-AB** (default; per-country zstd-compressed GeoPackages from the `laser-base/unocha` mirror, falling back to a 1–2 GB global geodatabase from HDX), **geoBoundaries** (per-country zips, pinned to `v6.0.0` — good for reproducibility), and **GADM** (per-country shapefile zip or GeoPackage, v4.1).

Porting all three is worthwhile — coverage genuinely varies by country and level, and the fallback chain is the kind of thing that only gets written after it has failed in the field. Two cautions. First, the UNOCHA global-geodatabase fallback should not be reachable by default in a library; a 1–2 GB download triggered implicitly by a `load`-shaped call is user-hostile. Second, **GADM is non-commercial-only**, which `laser-init` gets away with by never redistributing it. Given this package's careful `NOTICE.md`/`licenses/` posture, GADM must stay strictly fetch-at-runtime and never enter a bundled or release-asset tier. That constraint should be written into the source descriptor, not left to memory.

### 5.2 Population raster aggregation

`WorldPopExtractor` downloads 1 km gridded population, selecting between the `Global_2015_2030/R2025A` and `Global_2000_2020_1km_UNadj` products by year (`extractors/worldpop.py:79`). The transformers then aggregate the raster onto admin polygons via `rastertoolkit.raster_clip` (`utils.py:316`), keyed by p-code, and write `population` back onto the GeoDataFrame.

This is the single most valuable spatial capability in `laser-init` and the hardest to reproduce: it is what turns a boundary file into a metapopulation. Port it. `rastertoolkit`, `geopandas` and `pyogrio` should all be `[spatial]`-extra dependencies, imported lazily.

### 5.3 The interchange schema — and a lighter alternative

`laser-init`'s spatial output is a GeoPackage with `nodeid`, `name`, `population`, `geometry`, plus the source p-code and (for UNOCHA) `dot_name`. GeoPackage over shapefile/geodatabase is the right call and the reasoning is documented (`transformers/unocha.py:12`): one file, not a directory or a file set.

Two schema details deserve to survive the port. **P-codes** are the join key for subnational data across sources and years, and a flat display name is not a substitute. **`dot_name`** — the dotted hierarchical path — is what makes admin-2 units addressable and disambiguable. This package's flat `location` key (`Kenya`, `United_States`) will not survive admin-2, and `locations.csv` already carries an unused `level` column that is the natural place to start.

Beyond a straight port, there is a lighter primitive worth adding. `laser-init` always carries full geometry because it wants choropleths, but a metapopulation model mostly needs **centroids, areas, populations and a distance matrix** — not polygons. A **node table** (`nodeid`, `dot_name`, `pcode`, `lat`, `lon`, `area_km2`, `population`, `level`) for admin-0 and admin-1 worldwide would be a few MB, would fit tier 1, and would unlock gravity-model connectivity with **no `geopandas` dependency at all**.

**Decision: ship both, with the node table as the default.** `ssd.load_nodes('kenya', level=1)` returns the lightweight table and needs nothing beyond the base install; `ssd.fetch_shapes('kenya', level=1)` returns the full GeoDataFrame and requires `[spatial]`. *Built as `fetch_shapes`, not `load_shapes`: geometry is tier 2, and §2's rule is that anything which can touch the network gets a different verb from `load()`.* The node table is generated from the same boundary sources at build time, so the two are guaranteed consistent — the node table is a projection of the geometry, not an independent dataset, and `nodeid`/`pcode` join them. This keeps the common case free of `geopandas` while leaving nothing out for anyone who wants maps or exact areas.

### 5.4 Connectivity and the gravity model

`laser-init` exposes gravity parameters through the generated config (`gravity_k`, `gravity_a`, `gravity_b`, `gravity_c`, implementing $c_{ij} = k \cdot P_i^a P_j^b / D_{ij}^c$), with the distance computation living downstream in `laser.generic`, derived from the GeoPackage geometry. Starsim will need an equivalent when spatial mixing arrives.

The parameterisation is standard and worth adopting for consistency across IDM tools, but the *implementation* belongs in Starsim (as a spatial `Route`, alongside `ss.MixingPools`), not in a data package. What `starsim_data` should provide is the input: the node table of §5.3 plus a `distances()` helper. Drawing that line clearly now avoids the dependency inversion discussed in §6.

### 5.5 Level handling

`level_from_string` (§3.2) and the general `country × level × year` addressing model. Small, but it is the vocabulary the whole spatial tier is expressed in, and `locations.csv` should adopt it before it has rows at more than one level.

### 5.6 The data-source comparison documentation

`laser-init/docs/datasources.md` is ~480 lines comparing the sources on coverage, admin depth, update frequency, file size, license and regional strengths, with per-source citations and recommendations by use case and by region. This is accumulated judgement, not code, and it is the sort of thing nobody rewrites once lost. Port it more or less verbatim when the spatial sources land, and fold this package's existing per-source notes in `NOTICE.md` into the same structure. *Built as `docs/06-datasources.qmd`, one page of a full great-docs site (§9, decision 10).*

---

## 6. What not to port

- **LLM-based country resolution.** `openai_query.py` (389 lines) and `anthropic_query.py` (19 lines, and it only wraps the *local* matcher). The README concedes the feature is "not currently implemented," yet `openai` and `anthropic` are unconditional runtime dependencies, and `coverage.run` omits both files from measurement. A non-deterministic country resolver is the wrong tool regardless: the deterministic alias table of §3.2 covers the real cases, and warning with candidates is a better failure mode than a confident guess.
- **Model-script emission.** `loaders/abm.py`, `loaders/mpm.py`, `models/{si,sir,seir,plot}.py`. This makes `starsim_data` depend on Starsim, inverting the dependency a data package should have, and Starsim already has its own model-authoring story. **Decided: no `starsim-init` equivalent, here or elsewhere.** If templated scaffolding is ever wanted, `ss.Sim(location='kenya')` reading from `starsim_data` is the natural home for it, in Starsim.
- **Import-time configuration and logging side effects.** See §3.4.
- **Ruff — and any other lint config.** No linter is enforced in this repo. mkdocs is out too; the docs are built with great-docs (§9, decision 10).
- **`requests`, `rapidfuzz`, `pyyaml`, `click`, `pycountry` as runtime dependencies.** Every one has a sciris equivalent already installed (§3.8). Reimplement against sciris rather than translating the imports across.
- **The `error()` helper** (`utils.py:355`), which prints, logs, and raises an exception class passed as an argument. It is typed `NoReturn` but call sites still write post-`error()` fallbacks (`extractors/worldpop.py:73`), so the control flow reads as though it can return. Raise directly.
- **A 90%-coverage gate applied to a package that vendors 13 MB of data.** Adopt coverage reporting; set the threshold against what is actually meaningful to test here rather than inheriting the number.

---

## 7. Invariants to protect while porting

1. **`load()` never touches the network.** Every tier-1/tier-2 capability goes behind a different verb.
2. **Version-pinned data, versioned by upstream revision.** `starsim_data==X.Y.Z` returns byte-identical tier-0 data forever, and tier-1 assets are release-pinned, not "latest." Tier-0 demographics are additionally versioned by WPP revision (`demographics-2024.h5`, `demographics-2026.h5`, …) with `which='deaths'` resolving to the newest bundled revision and `revision=2024` pinning an older one. That way a new WPP release is an additive rebuild rather than a silent change to existing data, and old vintages stay reproducible for anyone mid-study.
3. **One new dependency group, not four.** Base install stays sciris-only in effect: `matplotlib`, `tqdm`, `zstandard` and `pyyaml` all arrive through sciris, and `requests`/`rapidfuzz`/`pycountry`/`click` are not needed at all (§3.8). The single optional extra is `[spatial]` (`geopandas`, `pyogrio`, `rastertoolkit`), lazily imported. `import starsim_data` must not import `geopandas`.
4. **Licensing hygiene.** Every new source gets a `NOTICE.md` entry, a `licenses/` file where required, and a machine-readable license field in its registry descriptor. GADM's non-commercial terms make this load-bearing, not ceremonial (§5.1).
5. **Starsim-native output.** Tidy `sciris.dataframe`s with UN-native column names that feed Starsim modules directly — never `laser.generic`'s schemas.

---

## 8. Prioritized plan

*Status: P0 shipped in 0.2.0, P1 in 0.3.0 (item 12 dropped — see decision 8), P2 in 0.4.0. See [CHANGELOG.md](../CHANGELOG.md).*

| # | Item | Source | Effort | New deps | Tier |
|---|---|---|---|---|---|
| **P0 — now; small, no new dependencies** ||||||
| 1 | Location resolution: normalization, alias tables, French names, `sc.suggest` candidates | `utils.py:31–144`, `french_iso.py` | S | — | 0 |
| 2 | Generate `iso3`/`official_name`/`aliases` into `locations.csv` at build time | new build script, `pycountry` dev-only | S | — | 0 |
| 3 | `level_from_string` and `country × level` addressing | `utils.py:147` | XS | — | 0 |
| 4 | Provenance in the HDF5 `spec` + `ssd.provenance()` | concept from `utils.py:257` | S | — | 0 |
| 5 | CI, pytest markers, `CHANGELOG.md` (no lint config) | `.github/` | S | — | — |
| 6 | Resolve the `ss.Births` `Time`/`Year` column mismatch (§3.1) | — | XS | — | 0 |
| 7 | Revision-versioned demographics (`demographics-2024.h5`, `revision=` arg) | invariant 2 | S | — | 0 |
| **P1 — next; still no new dependencies** ||||||
| 8 | Cached downloader on `sc.download` + cache-dir setting (no import-time config) | `utils.py:193`, reimplemented | S | — | 1–2 |
| 9 | Dataset registry + descriptors, replacing the layout if-chain | `registry.py`, `interfaces.py` | M | — | all |
| 10 | On-demand WPP fetch for annual data, life tables, other variants | `extractors/unwpp.py` | M | — | 2 |
| 11 | Validation plots: age pyramid, rate series, matrix heatmap | `cli.py:522–722` | S | — | 0 |
| ~~12~~ | ~~Thin CLI (`argparse`) over the library API~~ — **dropped on review**; the same surface is exposed as library calls instead (§9.8) | — | — | — | — |
| **P2 — spatial; design now, build when Starsim spatial lands** ||||||
| 13 | Node table (centroids, area, population) for admin 0/1 — the default | new; synthesis (§5.3) | M | — | 1 |
| 14 | Shape extractors + transformers (UNOCHA, geoBoundaries, GADM) | `extractors/`, `transformers/` | L | `[spatial]` | 2 |
| 15 | WorldPop raster + raster→admin aggregation | `extractors/worldpop.py`, `utils.py:316` | M | `[spatial]` | 2 |
| 16 | Full-geometry accessor alongside the node table (§5.3) | `transformers/*` | M | `[spatial]` | 2 |
| 17 | P-code / `dot_name` hierarchical keys; multi-level `locations.csv` | `transformers/unocha.py` | M | — | all |
| 18 | `distances()` helper for gravity-model input | §5.4 | S | — | 1 |
| 19 | `datasources.md` comparison, plus a full docs site | `docs/datasources.md`; great-docs | M | — | — |
| 20 | Choropleth plotting | `cli.py:491` | S | `[spatial]` | 2 |

---

## 9. Decisions

Resolved on review:

1. **The spatial tier lives in this package**, behind a `[spatial]` extra rather than in a sibling. One location resolver, one cache, one provenance story, no duplication. §3.8 strengthens this: since the only new dependencies in the entire plan are the three spatial libraries, the "optional surface dwarfs the core" objection mostly evaporates. If it ever does need to split, `starsim_geodata` depending on `starsim_data` is the shape — but there is no reason to pre-split.
2. **Both node table and full geometry**, node table as the default (§5.3). The node table is generated from the same sources at build time and joins to the geometry on `nodeid`/`pcode`, so they cannot drift.
3. **Do not wait on Starsim's spatial API.** Build the node table and `distances()` to the design in §5.3–5.4 now; adapt if the eventual spatial `Route` wants something different. The data shape is the more stable half of that interface.
4. **No `starsim-init` equivalent** (§6).
5. **Regenerate tier-0 demographics per WPP revision**, keeping old vintages loadable (invariant 2).
6. **No lint config** — not ruff, and not Starsim's `.flake8`/`pylint` either (§3.7).
7. **The `ss.Births` `Time`/`Year` mismatch is fixed in Starsim, not here** (§3.1). `ss.Deaths` and `ss.Pregnancy` both already use `Time`, so `ss.Births` is the inconsistent one, and fixing it upstream means this package needs no per-module special-casing. Handed off to the Starsim repo as a separate prompt and **since fixed there**; no `Year`-emitting workaround was added on this side.
8. **No CLI.** P1 item 12 is dropped. `laser-init` is a CLI with a library underneath; this is a library, and its users reach it from Python or from Starsim, not from a shell. Everything the CLI would have exposed is a library call instead — `list_datasets(detailed=True)`, `fetch()`, `plot()`, `cache_info()`, `clear_cache()`, `options` — which is also one fewer interface to document and keep in step. A CLI can be added later over that surface if a real use case turns up; the reverse is much harder.

9. **The node table bundles; it does not need a tier-1 release asset.** This was the last open question, and building one answered it: levels 0 and 1 for 184 countries is **3,254 nodes in 1.4 MB**, against a package that was already ~13 MB. So the node table joins tier 0, `load_nodes()` is offline and instant like `load()`, and tier 1 currently has no occupants at all — the tier stays in the model for subnational *demographics*, which would be far larger, but nothing needs it yet.

10. **The documentation site is built with [great-docs](https://posit-dev.github.io/great-docs/)**, not with Quarto directly and not with mkdocs. great-docs renders Quarto underneath, so the `.qmd` sources and the Starsim-adjacent toolchain are unchanged, but it additionally generates the API reference from the docstrings, which removes the need to maintain a reference section by hand. Narrative pages live in `docs/`, the configuration is `great-docs.yml`, and the build directory is gitignored. Item 19 grew accordingly, from one ported page to a nine-page site.

Still open:

- Nothing. P0–P2 are built; see [CHANGELOG.md](../CHANGELOG.md) for what shipped when.
