# Changelog

All notable changes to this project are documented in this file.

## 2026-07-30 — Nullable fields and degree-bounded relations

### Added
- `nullable` / `null_chance` options, usable on **any** field type in a
  table or on a join table's `fields:` block. On each row, a nullable
  field is blank (`""`) with probability `null_chance` (default `0.5`)
  instead of always calling its generator. Blank values never count
  against `unique: true`, matching how a real database allows multiple
  `NULL`s in a unique column.
- `min_per_left` / `max_per_left` on `1-N` relations, to guarantee (as
  closely as the table sizes allow) that every `left` value ends up with
  a connection count inside that range, instead of each `right` row
  independently picking any `left` value at random.
- `min_per_left` / `max_per_left` / `min_per_right` / `max_per_right` on
  `N-N` relations, switching the join from "generate `join_rows` random
  pairs" into a degree-controlled mode: each value's own target
  connection count is sampled within its bound, and edges are built up
  prioritizing whichever values haven't hit their minimum yet. Falls
  back to the original `join_rows`-based behavior when none of the four
  bounds are set.
- A `[warn]` is printed (with a count of affected values) whenever the
  requested min/max bounds turn out to be infeasible for the given table
  sizes, on both `1-N` and `N-N`.
- `config.succession_planning.yaml` — a new example config modeling an
  HR succession-planning schema (Role, Candidate, Skill, Goal, plus six
  relationship tables), demonstrating a hashed composite primary key on
  a join table and degree-bounded relations throughout.
- `CHANGELOG.md` (this file).

### Changed
- `config.example.yaml` now also demonstrates `phone`/`address`/`text`
  fields, a `nullable` field, a degree-bounded `1-N` relation, an `N-N`
  relation with its own extra column and renamed keys, and a self-join
  `N-N` relation (`referrals`) using `exclude_self`.
- README expanded with sections on `nullable`/`null_chance`, degree
  bounds, join-table `fields:`, and `left_as`/`right_as`/`exclude_self`.

### Removed
- The `optional_date` field type. It's superseded by the generic
  `nullable`/`null_chance` mechanism above, which works the same way but
  on every field type instead of just `date`. Existing configs using
  `type: optional_date` need to switch to `type: date` (or whatever the
  underlying type is) plus `nullable: true` and `null_chance: <value>`
  (equal to `1 - probability` from the old option).

### Fixed
- Fixed a broken f-string in `gen_phone` (an unterminated string literal
  split across two lines) that only surfaced when the `faker` package
  wasn't installed.

## Earlier — Attributed many-to-many relations

### Added
- `left_as` / `right_as` options on `N-N` relations, to rename the two
  key columns in the generated join table instead of the
  `"<table>_<field>"` default.
- `exclude_self` option on `N-N` relations, for self-joins (`left.table
  == right.table`, e.g. an org chart's "reports to" relationship) — skips
  pairs where both picks are the same value so a row never points at
  itself.
- `fields:` option on `N-N` relations, letting the join table carry its
  own extra columns (an attribute of the relationship itself, e.g. a
  required skill's proficiency level, a readiness score, milestone
  dates). Uses the same field mini-language as a table's `fields:` block,
  and can reference the join's own `left_as`/`right_as` columns — e.g.
  via `type: hash`, to build a composite primary key out of both sides
  of the link.
- New field types: `phone`, `address`, `text` (falls back to small
  built-in generators when `faker` isn't installed).
- `optional_date` field type (a `date` that's blank some of the time,
  controlled by a `probability` option) — later removed and replaced by
  the generic `nullable`/`null_chance` mechanism above.

## Initial version

- Config-driven table generation (`rows`, `fields`, `static_rows`).
- Field types: `name`, `number`, `boolean`, `email`, `date`, `choice`,
  `hash`.
- `unique: true` per-field uniqueness enforcement with retry.
- `1-1`, `1-N`, and `N-N` relations between tables (the latter via
  `join_rows` + `unique_pairs`).
- Optional `faker` integration for realistic names/emails; works with
  zero dependencies otherwise (aside from `pyyaml` for YAML configs).
