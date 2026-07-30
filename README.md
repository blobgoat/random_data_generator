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
   python generate_data.py --config input/config.example.yaml --outdir ./output --seed 42
   ```

   This writes one CSV per table (plus any join tables from many-to-many
   relations) into `./output`.

3. **(Optional) Dev requirements**: only needed if you want to
   type-check the script, not to run it. `requirements-dev.txt` installs:
   - `mypy` — the type checker itself
   - `types-PyYAML` — type stubs for `pyyaml`, so mypy can check the
     `import yaml` in `generate_data.py` instead of erroring with
     "Library stubs not installed for 'yaml'"

   ```bash
   pip install -r requirements-dev.txt
   mypy generate_data.py
   ```

### Command-line flags

| Flag | Required | Description |
|---|---|---|
| `--config` | yes | Path to your `.yaml`, `.yml`, or `.json` config file |
| `--outdir` | no | Where to write CSVs (default: `../output`) |
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
- `static_rows` is an alternative to `rows` for hard-coding some or all
  columns row-by-row (e.g. a fixed product catalog) while still randomly
  generating whatever you don't specify. See below.

### 2. Field types

| Type | Options | Notes |
|---|---|---|
| `name` | — | Full name. Realistic if `faker` is installed. |
| `email` | — | Random email address. Realistic if `faker` is installed. |
| `phone` | — | Random phone number. Realistic if `faker` is installed. |
| `address` | — | Random single-line street address. Realistic if `faker` is installed. |
| `text` | `sentences: <int>` (default 1) | Random free-text sentence(s) — handy for notes, abstracts, descriptions. |
| `number` | `digits: <int>` | Random integer with that many digits (e.g. `digits: 4` → 1000–9999). |
| `boolean` | — | Random `True`/`False`. |
| `date` | `start: "YYYY-MM-DD"`, `end: "YYYY-MM-DD"` | Random date in range. Both optional (defaults: `2000-01-01` to today). |
| `choice` | `values: [string, ...]` | **Custom type** — picks one of your strings at random for each row. See below. |
| `hash` | `fields: [string, ...]`, `algorithm`, `length`, `encoding` | Combines other fields from the same row into one deterministic hash — handy as a composite UID. See below. |

Every field type above also accepts `nullable`/`null_chance` (see below)
and `unique: true`.

### 2a. Making any field nullable

Add `nullable: true` to any field (of any type) to make it blank (`""`)
some of the time instead of always calling its generator. Set
`null_chance` (default `0.5`) to control how often — it's the
probability of being blank on any given row:

```yaml
fields:
  date_completed:
    type: date
    nullable: true
    null_chance: 0.6   # 60% chance of being blank; 40% chance of a date
    start: "2026-01-01"
    end: "2026-07-30"
```

A blank value never counts against `unique: true` — same as how a real
database allows more than one `NULL` in a `UNIQUE` column.

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

### 4. The `hash` type (composite UIDs)

Use `hash` to derive a single value from one or more *other* fields in
the same row — useful when you want a stable, deterministic UID built
out of data you're already generating, rather than a random one:

```yaml
fields:
  order_id:
    type: number
    digits: 6
    unique: true
  order_date:
    type: date
    start: "2025-01-01"
    end: "2026-07-16"
  status:
    type: choice
    values: ["pending", "shipped", "delivered", "cancelled"]
  row_uid:
    type: hash
    fields: [order_id, order_date, status]
    algorithm: sha256   # optional, default sha256 (any hashlib name works)
    length: 12          # optional, truncate the hex digest to N characters
    encoding: hex        # optional, "hex" (default) or "int"
```

Rules to know:

- `fields` must list column names declared **earlier in the same
  table**. `hash` can only see values already generated for the current
  row of the table it's defined in — it has no visibility into other
  tables. Referencing a field that lives in a different table (or one
  declared later in the same table) fails with an error telling you
  which name(s) weren't found.
- The hash is deterministic: the same combination of referenced field
  values always produces the same output. That makes `unique: true`
  only as useful as the referenced fields themselves are varied — if
  they collide, retrying the hash won't change the result, since it
  isn't random.
- `algorithm` accepts anything `hashlib.new()` supports (`sha256`,
  `sha1`, `md5`, `blake2b`, etc).
- Set `encoding: int` if you want an integer instead of a hex string.

#### Linking a hash across tables

A common mistake: wanting a hash on `orders` built from fields that
actually live on `users` (e.g. `customer_name`, `email`, `region`).
That won't work directly — `hash` can't reach into another table's
row. Instead, compute the hash **where its source fields already
live**, then use a relation (see below) to carry that value over, the
same way `user_id` gets attached to `orders` today:

```yaml
tables:
  users:
    rows: 100
    fields:
      customer_name:
        type: name
      email:
        type: email
      region:
        type: choice
        values: ["North America", "Europe", "Asia"]
      customer_id:
        type: hash
        fields: [customer_name, email, region]
        length: 12

  orders:
    rows: 300
    fields:
      order_id:
        type: number
        digits: 6
        unique: true
      # no customer_id declared here -- the relation below adds it

relations:
  - type: "1-N"
    left:
      table: users
      field: customer_id
    right:
      table: orders
      field: customer_id
```

`customer_id` is computed once per user from that user's own fields;
the `1-N` relation then assigns one of those values to each `orders`
row (with replacement, so one customer can have many orders). The
relation system copies values verbatim regardless of type, so a hash
column works as a relation key exactly like a plain numeric ID would.

### 5. `static_rows` (hard-coding rows)

Use `static_rows` when you want to hand-write some rows yourself — the
classic case is a fixed product catalog: you know the exact list of
product names, but you still want a random unique id and a random price
generated for each one:

```yaml
products:
  static_rows:
    - product_name: "Widget"
    - product_name: "Gadget"
    - product_name: "Gizmo"
  fields:
    product_id:
      type: number
      digits: 4
      unique: true
    product_name:
      type: name   # unused -- every row's name comes from static_rows
    price:
      type: number
      digits: 3
```

Rules to know:

- `static_rows` replaces `rows` — the table gets exactly as many rows as
  entries in the list (here, 3). If you also set `rows` and it doesn't
  match, it's ignored with a warning.
- Every column name used in `static_rows` must also be declared under
  `fields` (with a `type`, even if that type never actually runs because
  every row supplies the value directly — this keeps a single place
  that lists all of a table's columns).
- Per row, any declared field the static entry *doesn't* set still gets
  randomly generated as usual — that's how `product_id` and `price`
  above end up random even though `product_name` is fixed. You can mix
  and match per row too: one entry could pin `price` while another
  leaves it to be generated.
- `unique: true` fields are seeded with whatever static values you
  provided, so randomly-generated rows won't collide with your
  hard-coded ones.
- Because static values are filled in before generation proceeds
  through the rest of `fields`, a `hash` field can reference a static
  column the same way it references any other field (as long as it's
  declared earlier in `fields`).

### 6. Relations (optional)

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
| `N-N` | Neither table is modified. Instead, a brand-new join-table CSV is generated with pairs of `left.field` and `right.field`. |

For `1-1`/`1-N`, `left.field` and `right.field` must already exist as a
column on `left` (usually a `unique: true` id field) — `right.field` is
the *new* column name that gets created for you. For `N-N`, both fields
must already exist on their respective tables.

#### Controlling how many connections each row gets

By default, `1-N` just has each `right` row independently pick any
`left` value at random, and `N-N` just throws `join_rows` random pairs
at the wall — neither guarantees anything about how many connections any
individual row ends up with.

Set `min_per_left`/`max_per_left` (on `1-N` or `N-N`) — and, for `N-N`
only, `min_per_right`/`max_per_right` — to instead guarantee a
connection count in that range for every value on that side:

```yaml
relations:
  # Every user has 1-8 orders (instead of a random, uncontrolled spread).
  - type: "1-N"
    left: { table: users, field: user_id }
    right: { table: orders, field: user_id }
    min_per_left: 1
    max_per_left: 8

  # Every role requires 3-8 skills; every skill is required by 5-40 roles.
  - type: "N-N"
    left: { table: roles, field: role_id }
    right: { table: skills, field: skill_id }
    join_table: required_skills
    min_per_left: 3
    max_per_left: 8
    min_per_right: 5
    max_per_right: 40
```

Any of the four `N-N` bounds can be set independently — an unset bound
just means "no limit" on that side. Setting any of them switches that
relation from the old "just generate `join_rows` random pairs" mode
(which is still the default when none of these are set) into a
degree-controlled mode: each value's own target connection count is
picked at random within its `[min, max]`, and edges are built up
prioritizing whichever values haven't hit their minimum yet.

This is a best-effort process, not an exact solver — if the two tables'
sizes make the requested bounds mathematically infeasible (e.g.
`min_per_left` needs more distinct right-side values than exist), you'll
get a `[warn]` reporting how many values fell short, and you should
widen the range, loosen `unique_pairs`, or add more rows to the smaller
table.

#### Attaching extra columns to an `N-N` join table

`N-N` relations can also carry their own attributes — properties of the
*relationship* itself, not of either table individually (a required
skill's proficiency level, an order line's quantity, a succession
candidate's readiness score). Add a `fields:` block using the exact same
mini-language as a table's `fields:`:

```yaml
relations:
  - type: "N-N"
    left: { table: orders, field: order_id }
    right: { table: products, field: product_id }
    join_table: order_products
    fields:
      quantity:
        type: number
        digits: 1
```

`fields:` can also use `type: hash` to build a composite key out of both
sides of the link — see
[`input/config.succession_planning.yaml`](./input/config.succession_planning.yaml)'s
`Successor_Candidates` relation, which hashes `role_id` + `candidate_key`
together into a `successor_id` column.

#### Renaming join columns and self-joins

`left_as`/`right_as` (available on `N-N`) rename the two key columns in
the join table — handy since the default (`"<table>_<field>"`) can be
verbose, and necessary if you want a specific column name like `role_id`
rather than `Role_role_id`. `exclude_self: true` is for self-joins (when
`left.table` and `right.table` are the same table, e.g. an org chart's
"reports to" relationship) and stops a row from ever being paired with
itself:

```yaml
relations:
  - type: "N-N"
    left: { table: roles, field: role_id }
    right: { table: roles, field: role_id }
    join_table: reporting_lines
    left_as: role_id
    right_as: reports_to
    exclude_self: true
    min_per_left: 0
    max_per_left: 3
```

## Full examples

- [`input/config.example.yaml`](./input/config.example.yaml) — a compact
  tour of most features: four tables (`users`, `products`, `orders`,
  `referrals`), a degree-bounded `1-N` relation, an `N-N` relation with
  its own `quantity` column and renamed key columns, a self-join `N-N`
  with `exclude_self`, `choice` fields, a `hash` field, a `nullable`
  field, and a `static_rows` product catalog.
- [`input/config.succession_planning.yaml`](./input/config.succession_planning.yaml)
  — a larger, real-world-shaped example (an HR succession-planning data
  model: roles, candidates, skills, goals, and six relationship tables)
  that leans on degree-bounded relations throughout and a hashed
  composite primary key on one of its join tables.

## Extending it

To add a brand-new field type, write a
`gen_<type>(field_spec, rng, row)` function in `generate_data.py` and
register it in the `FIELD_GENERATORS` dict — see the comment above that
dict for details. `row` gives you the values already generated for
other fields in the same row (see `gen_hash` for an example that uses
it).

See [`CHANGELOG.md`](./CHANGELOG.md) for a history of what's been added.
