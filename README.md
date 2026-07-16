# random_data_generator

A small, dependency-optional command-line tool that generates realistic,
linked CSV data from a single YAML (or JSON) config file. Describe your
tables and columns once, and it writes out ready-to-use CSVs, including
foreign-key relationships between tables.

## Setup

1. **Requirements**: Python 3.9+. No packages are strictly required, but
   two optional ones make the output much better:
   - `pyyaml` — needed if your config file is `.yaml`/`.yml` (skip this
     and use a `.json` config if you don't want to install it)
   - `faker` — gives realistic names and emails; without it the script
     falls back to a small built-in list of first/last names

   Install both with:

   ```bash
   pip install -r requirements.txt
   ```

2. **Run it** against the bundled example:

   ```bash
   python generate_data.py --config config.example.yaml --outdir ./output --seed 42
   ```

   This writes one CSV per table (plus any join tables from many-to-many
   relations) into `./output`.

### Command-line flags

| Flag | Required | Description |
|---|---|---|
| `--config` | yes | Path to your `.yaml`, `.yml`, or `.json` config file |
| `--outdir` | no | Where to write CSVs (default: `./output`) |
| `--seed` | no | Integer seed for reproducible output. Omit for a different result every run |

## Setting up the YAML config

A config has up to two top-level sections: `tables` (required) and
`relations` (optional).

### 1. Define tables

Each table needs a row count and a set of fields (columns):

```yaml
tables:
  users:
    rows: 100
    fields:
      user_id:
        type: number
        digits: 5
        unique: true
      full_name:
        type: name
      email:
        type: email
      signup_date:
        type: date
        start: "2022-01-01"
        end: "2026-07-16"
      is_active:
        type: boolean
```

- `rows` — how many rows this table should have.
- `fields` — a map of `column_name: { type: ..., ...options }`.
- `unique: true` on any field re-rolls that value until it hasn't been
  used yet in that column (handy for IDs). If the field's possible value
  space is too small for the row count (e.g. `digits: 1` with 50 rows),
  generation will fail with a clear error telling you to widen the range.

### 2. Field types

| Type | Options | Notes |
|---|---|---|
| `name` | — | Full name. Realistic if `faker` is installed. |
| `email` | — | Random email address. Realistic if `faker` is installed. |
| `number` | `digits: <int>` | Random integer with that many digits (e.g. `digits: 4` → 1000–9999). |
| `boolean` | — | Random `True`/`False`. |
| `date` | `start: "YYYY-MM-DD"`, `end: "YYYY-MM-DD"` | Random date in range. Both optional (defaults: `2000-01-01` to today). |
| `choice` | `values: [string, ...]` | **Custom type** — picks one of your strings at random for each row. See below. |

### 3. The `choice` type (custom values)

Use `choice` whenever you want a column filled from your own list of
strings rather than one of the built-in generators. Supply 1 or more
strings under `values:`; each row independently gets one picked at
random (with replacement — the same value can appear in multiple rows):

```yaml
fields:
  plan_tier:
    type: choice
    values: ["free", "basic", "pro", "enterprise"]

  status:
    type: choice
    values: ["pending", "shipped", "delivered", "cancelled"]
```

A single value (`values: ["gold"]`) is valid too — every row just gets
`"gold"`. Combine with `unique: true` if you need each row to get a
distinct value from the list (in that case, the list must have at least
as many entries as the table has rows).

### 4. Relations (optional)

Relations link tables together like foreign keys:

```yaml
relations:
  - type: "1-N"
    left:
      table: users
      field: user_id
    right:
      table: orders
      field: user_id
```

| Type | Behavior |
|---|---|
| `1-1` | Every row in `right` gets a distinct value from `left`'s key column. A new column is created on `right`. |
| `1-N` | Many rows in `right` can share the same `left` value (normal foreign key). A new column is created on `right`. |
| `N-N` | Neither table is modified. Instead, a brand-new join-table CSV is generated with random pairs of `left.field` and `right.field`. Configure with `join_table` (output name), `join_rows` (row count), and `unique_pairs` (default `true`, no duplicate pairs). |

For `1-1`/`1-N`, `left.field` and `right.field` must already exist as a
column on `left` (usually a `unique: true` id field) — `right.field` is
the *new* column name that gets created for you. For `N-N`, both fields
must already exist on their respective tables.

## Full example

See [`config.example.yaml`](./config.example.yaml) for a complete,
runnable config with three tables (`users`, `products`, `orders`), a
`1-N` relation, an `N-N` relation, and two `choice` fields
(`plan_tier`, `status`).

## Extending it

To add a brand-new field type, write a `gen_<type>(field_spec, rng)`
function in `generate_data.py` and register it in the `FIELD_GENERATORS`
dict — see the comment above that dict for details.
