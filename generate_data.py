#!/usr/bin/env python3
"""
generate_data.py
=================

A configurable random-data generator that writes one or more linked CSV
files from a single JSON or YAML config file.

WHAT IT DOES
------------
1. You describe one or more "tables" in a config file. Each table lists
   the columns ("fields") you want and, for each field, a *type*
   (name / number / boolean / email / date) plus any type-specific
   options (like how many digits a number should have).

2. Any field can be marked ``unique: true``. When set, the generator
   keeps re-rolling that field until it produces a value that hasn't
   been used yet in that column, so you get valid unique IDs.

3. A table can hard-code some of its rows with `static_rows` instead of
   (or alongside) `rows: N` -- handy for things like a fixed product
   catalog where you want to list every product by name yourself but
   still have an id or price randomly generated for each one.

4. You can describe "relations" between two tables so that the CSVs
   reference each other, exactly like foreign keys in a real database:
       - "1-1"  every row in table A maps to exactly one row in table B
       - "1-N"  many rows in table A can point at the same row in table B
       - "N-N"  a brand-new join/bridge CSV is generated, containing
                random pairs of keys from both tables

USAGE
-----
    python generate_data.py --config config.example.yaml --outdir ./output

    Optional flags:
        --seed 42          # make the run reproducible
        --outdir ./output  # where CSVs get written (default: ./output)

See config.example.yaml in this folder for a full example, and the
"CONFIG FORMAT" comment block below for the field-by-field reference.


CONFIG FORMAT (YAML or JSON)
-----------------------------
tables:
  <table_name>:
    rows: <int>                      # how many rows to generate
    static_rows:                     # OPTIONAL: hard-code some rows
      - <column_name>: <value>       # instead of `rows: N`, provide N
        ...                          # of these -- row count = list
                                      # length. Each entry sets one or
                                      # more declared fields to a fixed
                                      # value for that row; any declared
                                      # field NOT set in the entry is
                                      # still randomly generated as usual
                                      # (every column named here must
                                      # also appear under `fields:` below)
    fields:
      <column_name>:
        type: name | number | boolean | email | date | choice | hash
        unique: true|false           # optional, default false

        # --- "number" specific options ---
        digits: <int>                # e.g. digits: 4 -> values 1000-9999

        # --- "date" specific options (both optional) ---
        start: "YYYY-MM-DD"          # default 2000-01-01
        end:   "YYYY-MM-DD"          # default today

        # --- "choice" specific options ---
        values: [<string>, ...]      # 1-n strings you provide; each row
                                      # gets one picked at random (with
                                      # replacement, so values can repeat
                                      # across rows unless unique: true)

        # --- "hash" specific options ---
        # Combines one or more OTHER fields from the same row into a
        # single deterministic hash -- handy as a composite/derived UID.
        # Referenced fields must be declared earlier in this table's
        # `fields:` list (so their value already exists for the row).
        fields: [<column_name>, ...]  # required, 1+ existing field names
        algorithm: sha256 | sha1 | md5 | blake2b | ...  # optional,
                                      # default sha256 (any hashlib name)
        length: <int>                 # optional, truncate the hex digest
                                       # to this many characters
        encoding: hex | int           # optional, default hex (string);
                                       # "int" returns the digest as an
                                       # integer instead

relations:
  - type: "1-1" | "1-N" | "N-N"

    # The "left" side is the table/field that already exists and is
    # being pointed AT (usually a primary key you defined above).
    left:
      table: <table_name>
      field: <column_name>

    # For "1-1" and "1-N": the "right" side is where a brand-new foreign
    # key column gets CREATED and filled in for you.
    #   "1-1" -> each right-table row gets a distinct left-table value
    #   "1-N" -> many right-table rows can share the same left-table value
    #
    # For "N-N": both left.field and right.field must already exist
    # (they're the two tables' primary keys). Nothing is added to either
    # table -- instead a new join-table CSV is generated with random
    # pairs of the two keys.
    right:
      table: <table_name>
      field: <column_name>

    # --- "N-N" specific options (ignored for 1-1 / 1-N) ---
    join_table: <name>       # optional, defaults to "<left>_<right>"
    join_rows: <int>         # optional, how many link rows to generate
    unique_pairs: true|false # optional, default true (no duplicate links)
"""

import argparse
import csv
import hashlib
import json
import random
import string
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# PyYAML is only needed if you use a .yaml/.yml config file. If it isn't
# installed we still work fine as long as you use a .json config.
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# Faker (https://pypi.org/project/Faker/) produces much more realistic
# names/emails than our built-in word lists. It's entirely optional --
# if it isn't installed we transparently fall back to the small built-in
# lists below, so this script has zero hard dependencies.
try:
    from faker import Faker
    _faker: "Faker | None" = Faker()
    _HAS_FAKER = True
except ImportError:
    _faker = None
    _HAS_FAKER = False


# ---------------------------------------------------------------------------
# Fallback word lists (only used when the `faker` package isn't installed)
# ---------------------------------------------------------------------------
_FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Amara",
    "Diego", "Priya", "Wei", "Fatima", "Liam", "Noah", "Olivia", "Emma",
    "Sofia",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Chen", "Nguyen", "Patel", "Kim", "Okafor",
]


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    """Load a JSON or YAML config file based on its extension."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        if not _HAS_YAML:
            raise RuntimeError(
                "PyYAML is not installed but a .yaml config was given. "
                "Run `pip install pyyaml` or use a .json config instead."
            )
        return yaml.safe_load(text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Field generators
# ---------------------------------------------------------------------------
# Each generator function has the signature:
#     generator(field_spec: dict, rng: random.Random, row: dict) -> value
#
# `field_spec` is the dict for that field straight out of the config
# (e.g. {"type": "number", "digits": 4, "unique": True}), `rng` is a
# random.Random instance so results are reproducible with --seed, and
# `row` holds the values already generated for OTHER fields in this same
# row (in field-declaration order) -- most generators ignore it, but it's
# what lets `hash` derive a value from its sibling fields.

def gen_name(field_spec: dict, rng: random.Random, row: dict):
    """Random full name."""
    if _HAS_FAKER and _faker is not None:
        return _faker.name()
    first = rng.choice(_FIRST_NAMES)
    last = rng.choice(_LAST_NAMES)
    return f"{first} {last}"


def gen_number(field_spec: dict, rng: random.Random, row: dict):
    """
    Random integer with a specific number of digits.

    `digits: 4` -> a value between 1000 and 9999 (no leading zero, so it
    reads naturally as a 4-digit number). `digits: 1` -> 0-9.
    """
    digits = int(field_spec.get("digits", 6))
    if digits <= 0:
        raise ValueError("`digits` must be a positive integer")
    if digits == 1:
        return rng.randint(0, 9)
    low = 10 ** (digits - 1)
    high = (10 ** digits) - 1
    return rng.randint(low, high)


def gen_boolean(field_spec: dict, rng: random.Random, row: dict):
    """Random True/False."""
    return rng.choice([True, False])


def gen_email(field_spec: dict, rng: random.Random, row: dict):
    """Random email address."""
    if _HAS_FAKER:
        return _faker.email() if _faker else None
    local = "".join(rng.choices(string.ascii_lowercase, k=8))
    domain = rng.choice(["example.com", "mail.com", "test.org"])
    return f"{local}@{domain}"


def gen_choice(field_spec: dict, rng: random.Random, row: dict):
    """
    Pick one random value out of a user-supplied list.

    This is the "custom type" -- you provide 1-n strings under `values:`
    and each row gets one chosen at random (with replacement), e.g.:

        status:
          type: choice
          values: ["pending", "shipped", "delivered", "cancelled"]
    """
    values = field_spec.get("values")
    if not values or not isinstance(values, list):
        raise ValueError(
            "`choice` fields require a non-empty `values` list, e.g. "
            "`values: [\"a\", \"b\", \"c\"]`"
        )
    return rng.choice(values)


def gen_date(field_spec: dict, rng: random.Random, row: dict):
    """Random date (as an ISO string) between `start` and `end`."""
    start = _parse_date(field_spec.get("start", "2000-01-01"))
    end = _parse_date(
        field_spec.get("end", date.today().isoformat())
    )
    span_days = (end - start).days
    if span_days < 0:
        raise ValueError("`start` date must be before `end` date")
    offset = rng.randint(0, span_days)
    return (start + timedelta(days=offset)).isoformat()


def gen_hash(field_spec: dict, rng: random.Random, row: dict):
    """
    Combine one or more already-generated fields from this same row into
    a single deterministic hash -- useful as a composite/derived UID.

    Config:
        row_uid:
          type: hash
          fields: ["order_id", "order_date", "status"]
          algorithm: sha256   # optional, default sha256 (any hashlib name)
          length: 12          # optional, truncate the hex digest
          encoding: hex       # optional, "hex" (default) or "int"

    The referenced fields must be declared EARLIER in this table's
    `fields:` list, since fields are generated top-to-bottom and this
    reads their already-generated values out of `row`. Note this is
    deterministic given those fields' values, so pairing it with
    `unique: true` only helps if the referenced fields vary enough to
    avoid collisions -- retries won't change the result on their own.
    """
    field_names = field_spec.get("fields")
    if not field_names or not isinstance(field_names, list):
        raise ValueError(
            "`hash` fields require a non-empty `fields` list naming the "
            "columns to combine, e.g. `fields: [\"user_id\", \"order_id\"]`"
        )
    missing = [name for name in field_names if name not in row]
    if missing:
        raise ValueError(
            f"`hash` field references field(s) {missing} that aren't "
            "available yet. Declare those fields earlier in this "
            "table's `fields:` list."
        )

    algorithm = field_spec.get("algorithm", "sha256")
    try:
        hasher = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(
            f"Unknown hash algorithm '{algorithm}'. Valid options include "
            f"{sorted(hashlib.algorithms_guaranteed)}"
        ) from None

    combined = "|".join(str(row[name]) for name in field_names)
    hasher.update(combined.encode("utf-8"))
    digest = hasher.hexdigest()

    length = field_spec.get("length")
    if length is not None:
        digest = digest[:int(length)]

    if field_spec.get("encoding", "hex") == "int":
        return int(digest, 16)
    return digest


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


# Registry mapping the `type:` string in the config to its generator
# function. Add your own entry here (e.g. "phone": gen_phone) to extend
# the tool with new field types.
FIELD_GENERATORS = {
    "name": gen_name,
    "number": gen_number,
    "boolean": gen_boolean,
    "email": gen_email,
    "date": gen_date,
    "choice": gen_choice,
    "hash": gen_hash,
}

# Safety valve: how many times we'll retry a field before giving up on
# finding a fresh unique value (protects against e.g. `digits: 1` +
# `unique: true` + 50 rows, which is mathematically impossible).
MAX_UNIQUE_ATTEMPTS = 10_000


def generate_field_value(field_name: str, field_spec: dict,
                         rng: random.Random, used_values: set, row: dict):
    """Generate one value for a field, honoring `unique: true` if set."""
    ftype = field_spec.get("type")
    if ftype not in FIELD_GENERATORS:
        raise ValueError(
            f"Unknown field type '{ftype}' for field '{field_name}'. "
            f"Valid types: {sorted(FIELD_GENERATORS)}"
        )
    generator = FIELD_GENERATORS[ftype]

    if not field_spec.get("unique", False):
        return generator(field_spec, rng, row)

    for _ in range(MAX_UNIQUE_ATTEMPTS):
        value = generator(field_spec, rng, row)
        if value not in used_values:
            used_values.add(value)
            return value

    raise RuntimeError(
        f"Could not generate a unique value for field '{field_name}' after "
        f"{MAX_UNIQUE_ATTEMPTS} attempts. Increase `digits`, widen the "
        f"date range, or reduce the row count for this table."
    )


# ---------------------------------------------------------------------------
# Table generation
# ---------------------------------------------------------------------------
def generate_table(
    table_name: str, table_spec: dict, rng: random.Random
) -> dict:
    """
    Build one table's data.

    Returns a dict of {column_name: [values...]} -- i.e. columns stored
    as parallel lists, which makes it cheap to append new foreign-key
    columns later when relations are applied.

    Normally every field on every row is randomly generated. If the
    table also has a `static_rows` list, each entry in it hard-codes one
    or more column values for exactly one row (see `static_rows` below)
    -- any field NOT covered by that entry still falls back to its
    normal generator.
    """
    fields = table_spec.get("fields", {})
    if not fields:
        raise ValueError(f"Table '{table_name}' has no fields defined")

    static_rows = table_spec.get("static_rows")
    if static_rows is not None:
        if not isinstance(static_rows, list) or not static_rows:
            raise ValueError(
                f"Table '{table_name}': `static_rows` must be a "
                "non-empty list of {column_name: value} rows"
            )
        for i, entry in enumerate(static_rows):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Table '{table_name}': `static_rows[{i}]` must be a "
                    "mapping of column_name: value"
                )
            unknown = [name for name in entry if name not in fields]
            if unknown:
                raise ValueError(
                    f"Table '{table_name}': `static_rows[{i}]` sets "
                    f"undeclared column(s) {unknown}. Every column used "
                    "in `static_rows` must also be declared under "
                    "`fields`."
                )
        declared_rows = table_spec.get("rows")
        if declared_rows is not None and int(declared_rows) != len(static_rows):
            print(
                f"[warn] table '{table_name}': `rows: {declared_rows}` is "
                f"ignored in favor of `static_rows`'s {len(static_rows)} "
                "entries."
            )
        row_count = len(static_rows)
    else:
        row_count = int(table_spec.get("rows", 0))

    columns: dict[str, list] = {field_name: [] for field_name in fields}
    used_values_by_field: dict[str, set] = {
        field_name: set()
        for field_name, spec in fields.items()
        if spec.get("unique", False)
    }
    # Seed uniqueness tracking with any values supplied via `static_rows`
    # so randomly-generated rows don't collide with the ones you already
    # hard-coded.
    if static_rows:
        for entry in static_rows:
            for field_name, value in entry.items():
                if field_name in used_values_by_field:
                    used_values_by_field[field_name].add(value)

    for i in range(row_count):
        static_entry = static_rows[i] if static_rows else {}
        row: dict = {}
        for field_name, field_spec in fields.items():
            if field_name in static_entry:
                value = static_entry[field_name]
            else:
                if "type" not in field_spec:
                    raise ValueError(
                        f"Table '{table_name}', row {i}: field "
                        f"'{field_name}' has no static value and no "
                        "`type` to generate one. Either add it to every "
                        "`static_rows` entry or give it a `type`."
                    )
                used_values = used_values_by_field.get(field_name, set())
                value = generate_field_value(field_name, field_spec, rng,
                                             used_values, row)
            row[field_name] = value
            columns[field_name].append(value)

    return columns


# ---------------------------------------------------------------------------
# Relations: 1-1, 1-N, N-N
# ---------------------------------------------------------------------------
def _row_count(columns: dict) -> int:
    """How many rows a table currently has, based on its first column."""
    if not columns:
        return 0
    return len(next(iter(columns.values())))


def apply_relation_one_to_one(tables: dict, rel: dict, rng: random.Random):
    """
    Every row of the right table gets paired with a DISTINCT value from
    the left table's key column. If the two tables don't have the same
    number of rows, we pair as many as we can and leave the rest blank.
    """
    left_table, left_field = rel["left"]["table"], rel["left"]["field"]
    right_table, right_field = rel["right"]["table"], rel["right"]["field"]

    left_values = list(tables[left_table][left_field])
    rng.shuffle(left_values)

    right_rows = _row_count(tables[right_table])
    if right_rows != len(left_values):
        print(
            f"[warn] 1-1 relation {left_table}.{left_field} -> "
            f"{right_table}.{right_field}: row counts differ "
            f"({len(left_values)} vs {right_rows}); extra rows will be" +
            " left blank."
        )

    paired = left_values[:right_rows]
    # Pad with blanks if the right table has more rows than we have keys for.
    paired += [""] * (right_rows - len(paired))
    tables[right_table][right_field] = paired


def apply_relation_one_to_many(tables: dict, rel: dict, rng: random.Random):
    """
    Each row of the right ("many") table is randomly assigned one value
    from the left ("one") table's key column, WITH replacement -- so
    several right-table rows can end up pointing at the same left-table
    row, which is exactly what a normal foreign key looks like.
    """
    left_table, left_field = rel["left"]["table"], rel["left"]["field"]
    right_table, right_field = rel["right"]["table"], rel["right"]["field"]

    left_values = tables[left_table][left_field]
    right_rows = _row_count(tables[right_table])

    tables[right_table][right_field] = [
        rng.choice(left_values) for _ in range(right_rows)
    ]


def apply_relation_many_to_many(
    tables: dict, rel: dict, rng: random.Random
) -> tuple:
    """
    Generates a brand-new join/bridge table linking `left.field` values
    to `right.field` values. Neither original table is modified.

    Returns (join_table_name, join_table_columns) so the caller can write
    it out as its own CSV alongside the other tables.
    """
    left_table, left_field = rel["left"]["table"], rel["left"]["field"]
    right_table, right_field = rel["right"]["table"], rel["right"]["field"]

    left_values = tables[left_table][left_field]
    right_values = tables[right_table][right_field]

    join_table_name = rel.get("join_table", f"{left_table}_{right_table}")
    default_join_rows = max(len(left_values), len(right_values))
    join_rows = int(rel.get("join_rows", default_join_rows))
    unique_pairs = rel.get("unique_pairs", True)

    left_col = f"{left_table}_{left_field}"
    right_col = f"{right_table}_{right_field}"

    pairs: set[tuple] | None = set() if unique_pairs else None
    left_out: list[Any] = []
    right_out: list[Any] = []

    max_possible = len(left_values) * len(right_values)
    if unique_pairs and join_rows > max_possible:
        print(
            f"[warn] N-N relation {join_table_name}: requested {join_rows} "
            f"unique pairs but only {max_possible} distinct pairs are "
            f"possible; generating {max_possible} instead."
        )
        join_rows = max_possible

    attempts = 0
    while len(left_out) < join_rows and attempts < join_rows * 50 + 1000:
        attempts += 1
        left_val: Any = rng.choice(left_values)
        right_val: Any = rng.choice(right_values)
        if unique_pairs:
            assert pairs is not None
            if (left_val, right_val) in pairs:
                continue
            pairs.add((left_val, right_val))
        left_out.append(left_val)
        right_out.append(right_val)

    return join_table_name, {left_col: left_out, right_col: right_out}


def apply_relations(tables: dict, relations: list, rng: random.Random) -> dict:
    """
    Processes every relation in the config in order. 1-1 and 1-N relations
    add a new foreign-key column directly onto the "right" table. N-N
    relations produce an entirely new join table, collected and returned
    in `join_tables` so the caller can write them out too.
    """
    join_tables = {}

    for rel in relations:
        rtype = rel.get("type")
        if rtype == "1-1":
            apply_relation_one_to_one(tables, rel, rng)
        elif rtype == "1-N":
            apply_relation_one_to_many(tables, rel, rng)
        elif rtype == "N-N":
            name, columns = apply_relation_many_to_many(tables, rel, rng)
            join_tables[name] = columns
        else:
            raise ValueError(
                f"Unknown relation type '{rtype}' "
                "(expected 1-1, 1-N, or N-N)"
            )

    return join_tables


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------
def write_csv(path: Path, columns: dict):
    """Write a {column_name: [values...]} dict out as a CSV file."""
    fieldnames = list(columns.keys())
    row_count = _row_count(columns)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for i in range(row_count):
            writer.writerow([columns[name][i] for name in fieldnames])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    """
    Main entry point for the random data generator.

    Parses command-line arguments, loads the configuration, generates
    tables and relations, and writes the resulting CSV files to the
    specified output directory.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generate random, optionally-linked CSV data from a config "
            "file."
        )
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to a JSON or YAML config file",
    )
    parser.add_argument(
        "--outdir", default="../output",
        help="Directory to write CSVs into",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducible output",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    if _HAS_FAKER and args.seed is not None:
        Faker.seed(args.seed)

    config = load_config(Path(args.config))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # 1. Generate every table's own fields first (no foreign keys yet).
    tables = {}
    for table_name, table_spec in config.get("tables", {}).items():
        print(f"Generating table '{table_name}'...")
        tables[table_name] = generate_table(table_name, table_spec, rng)
        print(f"  -> {_row_count(tables[table_name])} rows")

    # 2. Apply relations: fills in FK columns for 1-1/1-N, and builds any
    #    N-N join tables.
    join_tables = apply_relations(tables, config.get("relations", []), rng)

    # 3. Write every table (including generated join tables) to CSV.
    for table_name, columns in {**tables, **join_tables}.items():
        out_path = outdir / f"{table_name}.csv"
        write_csv(out_path, columns)
        print(f"Wrote {out_path} ({_row_count(columns)} rows)")

    if not _HAS_FAKER:
        print(
            "\n[note] The 'faker' package isn't installed, so 'name' and "
            "'email' fields used a small built-in word list. "
            "`pip install faker` for more realistic/varied data."
        )


if __name__ == "__main__":
    main()
