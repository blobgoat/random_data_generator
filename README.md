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
| `number` | `digits: <int>` | Random integer with that many digits (e.g. `digits: 4` → 1000–9999). |
| `boolean` | — | Random `True`/`False`. |
| `date` | `start: "YYYY-MM-DD"`, `end: "YYYY-MM-DD"` | Random date in range. Both optional (defaults: `2000-01-01` to today). |
| `choice` | `values: [string, ...]` | **Custom type** — picks one of your strings at random for each row. See below. |
| `hash` | `fields: [string, ...]`, `algorithm`, `length`, `encoding` | Combines other fields from the same row into one deterministic hash — handy as a composite UID. See below. |

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
| `N-N` | Neither table is modified. Instead, a brand-new join-table CSV is generated with random pairs of `left.field` and `right.field`. Configure with `join_table` (output name), `join_rows` (row count), and `unique_pairs` (default `true`, no duplicate pairs). |

For `1-1`/`1-N`, `left.field` and `right.field` must already exist as a
column on `left` (usually a `unique: true` id field) — `right.field` is
the *new* column name that gets created for you. For `N-N`, both fields
must already exist on their respective tables.

## Full example

See [`input/config.example.yaml`](./input/config.example.yaml) for a
complete, runnable config with three tables (`users`, `products`,
`orders`), a `1-N` relation, an `N-N` relation, two `choice` fields
(`plan_tier`, `status`), a `hash` field (`row_uid`), and a `static_rows`
product catalog with a randomly generated id and price per product.

## Extending it

To add a brand-new field type, write a
`gen_<type>(field_spec, rng, row)` function in `generate_data.py` and
register it in the `FIELD_GENERATORS` dict — see the comment above that
dict for details. `row` gives you the values already generated for
other fields in the same row (see `gen_hash` for an example that uses
it).
