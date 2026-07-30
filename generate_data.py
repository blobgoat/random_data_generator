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
        type: name | number | boolean | email | date | choice | hash |
              phone | address | text
        unique: true|false           # optional, default false

        # --- nullable, works on ANY field type ---
        nullable: true|false         # optional, default false. If true,
                                      # this field is blank ("") some of
                                      # the time instead of always calling
                                      # its normal generator.
        null_chance: <0.0-1.0>       # optional, default 0.5. Probability
                                      # of being blank on any given row,
                                      # only used when nullable: true.
                                      # (Blank values never count against
                                      # `unique: true`'s uniqueness check,
                                      # same as NULL in a real database.)

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

    # --- "1-N" specific options ---
    min_per_left: <int>      # optional. Minimum number of right-table rows
                              # each left-table value must end up with.
    max_per_left: <int>      # optional. Maximum number of right-table rows
                              # each left-table value may end up with.
                              # If NEITHER is given, each right row just
                              # picks any left value independently at
                              # random (the original behavior) -- no
                              # guarantee about how many rows any one left
                              # value ends up with. If the right table's
                              # fixed row count can't exactly satisfy the
                              # requested min/max for every left value, the
                              # generator does its best and prints a
                              # [warn] describing the shortfall/overflow.

    # --- "N-N" specific options (ignored for 1-1 / 1-N) ---
    join_table: <name>       # optional, defaults to "<left>_<right>"
    join_rows: <int>         # optional, how many link rows to generate.
                              # Ignored if any of the min_per_*/max_per_*
                              # options below are set.
    unique_pairs: true|false # optional, default true (no duplicate links)
    left_as: <column_name>   # optional, rename the left key column in the
                              # join table (default "<left_table>_<field>")
    right_as: <column_name>  # optional, same idea for the right key column
    exclude_self: true|false # optional, default false. When left_table and
                              # right_table are the SAME table (a self-join,
                              # e.g. an org-chart "reports_to" table), set
                              # this to skip pairs where the two picks are
                              # identical so a row never points at itself.
    min_per_left: <int>      # optional. Minimum number of join rows each
    max_per_left: <int>      # optional. left-table value must appear in.
    min_per_right: <int>     # optional. Same idea, but counting how many
    max_per_right: <int>     # optional. join rows each right-table value
                              # appears in.
                              # Any of these four may be set independently;
                              # an unset bound is treated as "no limit" on
                              # that side. Setting any of them switches the
                              # join from the old "just generate join_rows
                              # random pairs" mode into a degree-controlled
                              # mode that tries to give every left/right
                              # value a connection count inside its bounds
                              # (each value's own target degree is chosen
                              # uniformly at random within [min, max]).
                              # This is a best-effort process -- if the two
                              # tables' sizes make the requested bounds
                              # infeasible (e.g. min_per_left too high for
                              # how many right values exist), a [warn] is
                              # printed reporting how many values fell
                              # short of their minimum.
    fields:                  # optional -- attach extra columns to the join
                              # table itself, e.g. a relationship's own
                              # attributes (a skill "level", a
                              # "readiness_score", dates). Uses the exact
                              # same mini-language as a table's `fields:`
                              # block above, and can reference the join's
                              # own left_as/right_as columns (e.g. via
                              # `type: hash`) to build a composite key from
                              # both sides of the link.
      <column_name>:
        type: ...
        ...
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


def gen_phone(field_spec: dict, rng: random.Random, row: dict):
    """Random phone number."""
    if _HAS_FAKER and _faker is not None:
        return _faker.phone_number()
    area = rng.randint(200, 999)
    prefix = rng.randint(200, 999)
    line = rng.randint(1000, 9999)
    return f"({area}) {prefix}-{line}"


def gen_address(field_spec: dict, rng: random.Random, row: dict):
    """Random street address (single line)."""
    if _HAS_FAKER and _faker is not None:
        return _faker.address().replace("\n", ", ")
    state = rng.choice(["CA", "TX", "NY", "OH", "WA", "IL", "CO", "GA"])
    return (
        f"{rng.randint(100, 9999)} Main St, Springfield, {state} "
        f"{rng.randint(10000, 99999)}"
    )


_TEXT_FALLBACK_WORDS = [
    "deliver", "strategic", "cross-functional", "leadership", "initiative",
    "stakeholder", "execution", "capability", "impact", "scalable",
    "customer-focused", "operational", "growth", "collaborative", "roadmap",
]


def gen_text(field_spec: dict, rng: random.Random, row: dict):
    """
    Random free-text sentence(s) -- useful for abstract statements,
    interpretations, notes, etc.

        interpretation:
          type: text
          sentences: 2   # optional, default 1
    """
    sentences = int(field_spec.get("sentences", 1))
    if _HAS_FAKER and _faker is not None:
        return " ".join(_faker.sentence() for _ in range(sentences))
    out = []
    for _ in range(sentences):
        words = rng.choices(_TEXT_FALLBACK_WORDS, k=7)
        out.append(" ".join(words).capitalize() + ".")
    return " ".join(out)


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
    "phone": gen_phone,
    "address": gen_address,
    "text": gen_text,
}

# Safety valve: how many times we'll retry a field before giving up on
# finding a fresh unique value (protects against e.g. `digits: 1` +
# `unique: true` + 50 rows, which is mathematically impossible).
MAX_UNIQUE_ATTEMPTS = 10_000


def generate_field_value(field_name: str, field_spec: dict,
                         rng: random.Random, used_values: set, row: dict):
    """
    Generate one value for a field, honoring `unique: true` and
    `nullable: true` if set.

    `nullable: true` works on top of ANY field type -- on each row, before
    calling the type's generator at all, we roll against `null_chance`
    (default 0.5) and return "" if it hits. A blank value is never checked
    against `used_values`, since (like a real database) multiple NULLs in
    a "unique" column are fine -- it's only non-blank duplicates we guard
    against.
    """
    ftype = field_spec.get("type")
    if ftype not in FIELD_GENERATORS:
        raise ValueError(
            f"Unknown field type '{ftype}' for field '{field_name}'. "
            f"Valid types: {sorted(FIELD_GENERATORS)}"
        )
    generator = FIELD_GENERATORS[ftype]

    nullable = field_spec.get("nullable", False)
    null_chance = float(field_spec.get("null_chance", 0.5))
    if nullable and not (0.0 <= null_chance <= 1.0):
        raise ValueError(
            f"`null_chance` for field '{field_name}' must be between 0 "
            "and 1"
        )

    if not field_spec.get("unique", False):
        if nullable and rng.random() < null_chance:
            return ""
        return generator(field_spec, rng, row)

    for _ in range(MAX_UNIQUE_ATTEMPTS):
        if nullable and rng.random() < null_chance:
            return ""
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
        if (
            declared_rows is not None
            and int(declared_rows) != len(static_rows)
        ):
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


def _assign_with_degree_bounds(
    pool: list, slot_count: int, min_deg: int, max_deg: int,
    rng: random.Random, context: str,
) -> list:
    """
    Fill `slot_count` slots with values from `pool` such that every
    DISTINCT value in `pool` ends up used between `min_deg` and `max_deg`
    times, as closely as this is possible given `slot_count`.

    Two-phase greedy approach:
      1. Hand out `min_deg` copies of every pool value first (in random
         order), so minimums are met whenever there's room for them.
      2. Randomly fill any remaining slots, preferring values that
         haven't hit `max_deg` yet.

    If `slot_count` can't fit every value's minimum, or exceeds what
    every value's maximum can absorb, we do our best and print a [warn]
    -- this is a best-effort random fill, not a strict solver.
    """
    pool_unique = list(dict.fromkeys(pool))
    n = len(pool_unique)
    if n == 0:
        raise ValueError(f"{context}: left table has no rows to assign from")
    if min_deg > max_deg:
        raise ValueError(
            f"{context}: min_per_left ({min_deg}) > max_per_left ({max_deg})"
        )

    if min_deg * n > slot_count:
        print(
            f"[warn] {context}: min_per_left={min_deg} would need at least "
            f"{min_deg * n} rows on the many side, but only {slot_count} "
            "exist; some left values will end up below the minimum."
        )
    if max_deg * n < slot_count:
        print(
            f"[warn] {context}: max_per_left={max_deg} allows at most "
            f"{max_deg * n} rows on the many side, but {slot_count} need "
            "assigning; some left values will exceed the maximum so every "
            "row still gets a value."
        )

    remaining = {v: 0 for v in pool_unique}
    assignments: list = []

    order = pool_unique[:]
    rng.shuffle(order)
    for v in order:
        if len(assignments) >= slot_count:
            break
        give = min(min_deg, slot_count - len(assignments))
        assignments.extend([v] * give)
        remaining[v] += give

    while len(assignments) < slot_count:
        candidates = [v for v in pool_unique if remaining[v] < max_deg]
        if not candidates:
            # Everyone is already at max_deg but rows remain -- ignore the
            # cap so every row still gets assigned a value.
            candidates = pool_unique
        v = rng.choice(candidates)
        assignments.append(v)
        remaining[v] += 1

    rng.shuffle(assignments)
    return assignments[:slot_count]


def apply_relation_one_to_many(tables: dict, rel: dict, rng: random.Random):
    """
    Each row of the right ("many") table gets one value from the left
    ("one") table's key column, WITH replacement -- so several
    right-table rows can end up pointing at the same left-table row,
    which is exactly what a normal foreign key looks like.

    By default (no `min_per_left`/`max_per_left`), each right row just
    picks any left value independently at random, with no guarantee about
    how many rows end up pointing at any one left value. Set
    `min_per_left` and/or `max_per_left` to instead cap/guarantee how many
    right-table rows each left value gets, e.g. "every role has 2-5
    candidates."
    """
    left_table, left_field = rel["left"]["table"], rel["left"]["field"]
    right_table, right_field = rel["right"]["table"], rel["right"]["field"]

    left_values = tables[left_table][left_field]
    right_rows = _row_count(tables[right_table])

    min_per_left = rel.get("min_per_left")
    max_per_left = rel.get("max_per_left")

    if min_per_left is None and max_per_left is None:
        tables[right_table][right_field] = [
            rng.choice(left_values) for _ in range(right_rows)
        ]
        return

    min_per_left = int(min_per_left) if min_per_left is not None else 0
    max_per_left = (
        int(max_per_left) if max_per_left is not None else right_rows
    )
    context = f"1-N {left_table}.{left_field} -> {right_table}.{right_field}"
    tables[right_table][right_field] = _assign_with_degree_bounds(
        left_values, right_rows, min_per_left, max_per_left, rng, context
    )


def _random_pairs_by_count(
    left_values: list, right_values: list, join_rows: int,
    unique_pairs: bool, exclude_self: bool, join_table_name: str,
    rng: random.Random,
) -> list:
    """
    Original N-N strategy: just throw `join_rows` random (left, right)
    darts, keeping only unique ones if `unique_pairs` is set. No control
    over how many times any individual left/right value shows up.
    """
    max_possible = len(left_values) * len(right_values)
    if exclude_self:
        # Rough upper bound once same-value pairs are excluded.
        max_possible = max(max_possible - len(left_values), 0)
    if unique_pairs and join_rows > max_possible:
        print(
            f"[warn] N-N relation {join_table_name}: requested {join_rows} "
            f"unique pairs but only {max_possible} distinct pairs are "
            f"possible; generating {max_possible} instead."
        )
        join_rows = max_possible

    pairs_seen: set = set() if unique_pairs else set()
    edges: list = []
    attempts = 0
    while len(edges) < join_rows and attempts < join_rows * 50 + 1000:
        attempts += 1
        left_val = rng.choice(left_values)
        right_val = rng.choice(right_values)
        if exclude_self and left_val == right_val:
            continue
        if unique_pairs:
            if (left_val, right_val) in pairs_seen:
                continue
            pairs_seen.add((left_val, right_val))
        edges.append((left_val, right_val))
    return edges


def _random_pairs_by_degree(
    left_values: list, right_values: list,
    min_per_left, max_per_left, min_per_right, max_per_right,
    unique_pairs: bool, exclude_self: bool, join_table_name: str,
    rng: random.Random,
) -> list:
    """
    Degree-controlled N-N strategy: every left/right value is first given
    its own random target connection count within its [min, max] bound
    (an unset bound on a side means "no limit" on that side), and edges
    are then built up randomly, always favoring values that still need
    more connections, until both sides' targets are used up.

    This is a best-effort greedy fill, not an exact solver -- if the two
    tables' sizes make the requested bounds infeasible (say, min_per_left
    needs more distinct right values than exist), some values will end up
    short of their minimum and a [warn] reports how many.
    """
    left_unique = list(dict.fromkeys(left_values))
    right_unique = list(dict.fromkeys(right_values))

    min_l = int(min_per_left) if min_per_left is not None else 0
    max_l = (
        int(max_per_left)
        if (max_per_left is not None)
        else len(right_unique)
    )
    min_r = int(min_per_right) if min_per_right is not None else 0
    max_r = (
        int(max_per_right)
        if max_per_right is not None
        else len(left_unique)
    )

    if min_l > max_l:
        raise ValueError(
            f"{join_table_name}: min_per_left ({min_l}) > "
            f"max_per_left ({max_l})"
        )
    if min_r > max_r:
        raise ValueError(
            f"{join_table_name}: min_per_right ({min_r}) > "
            f"max_per_right ({max_r})"
        )

    remaining_left = {v: rng.randint(min_l, max_l) for v in left_unique}
    remaining_right = {v: rng.randint(min_r, max_r) for v in right_unique}
    target_edges = min(sum(remaining_left.values()),
                       sum(remaining_right.values()))

    achieved_left: dict = {v: 0 for v in left_unique}
    achieved_right: dict = {v: 0 for v in right_unique}
    pairs_seen: set = set()
    edges: list = []
    attempts = 0
    max_attempts = target_edges * 30 + 5000
    while len(edges) < target_edges and attempts < max_attempts:
        attempts += 1
        left_active = [v for v, n in remaining_left.items() if n > 0]
        right_active = [v for v, n in remaining_right.items() if n > 0]
        if not left_active or not right_active:
            break
        # Prioritize whichever values haven't hit their OWN minimum yet,
        # so the limited edge budget goes to unmet minimums before
        # anyone gets "bonus" edges beyond their minimum. Without this,
        # pure random pairing can easily leave some values short even
        # when the totals are large enough to cover every minimum.
        left_needy = [v for v in left_active if achieved_left[v] < min_l]
        right_needy = [v for v in right_active if achieved_right[v] < min_r]
        left_pool = left_needy or left_active
        right_pool = right_needy or right_active

        left_val = rng.choice(left_pool)
        right_val = rng.choice(right_pool)
        if exclude_self and left_val == right_val:
            continue
        if unique_pairs and (left_val, right_val) in pairs_seen:
            continue
        if unique_pairs:
            pairs_seen.add((left_val, right_val))
        remaining_left[left_val] -= 1
        remaining_right[right_val] -= 1
        achieved_left[left_val] += 1
        achieved_right[right_val] += 1
        edges.append((left_val, right_val))

    short_left = sum(
        1 for v in left_unique if achieved_left.get(v, 0) < min_l
    )
    short_right = sum(
        1 for v in right_unique if achieved_right.get(v, 0) < min_r
    )
    if short_left or short_right:
        print(
            f"[warn] N-N relation {join_table_name}: could not fully "
            f"satisfy degree minimums -- {short_left} left value(s) below "
            f"min_per_left={min_l}, {short_right} right value(s) below "
            f"min_per_right={min_r}. Try widening the min/max range, "
            "relaxing unique_pairs, or adding more rows to the smaller "
            "table."
        )

    return edges


def apply_relation_many_to_many(
    tables: dict, rel: dict, rng: random.Random
) -> tuple:
    """
    Generates a brand-new join/bridge table linking `left.field` values
    to `right.field` values. Neither original table is modified.

    Optionally also generates extra per-row columns on the join table
    itself (via `fields:`), and can rename the two key columns (via
    `left_as` / `right_as`) or skip self-pairs on a self-join (via
    `exclude_self: true`).

    Two ways to control how many join rows get generated:
      - `join_rows` (+ `unique_pairs`): just generate that many random
        pairs -- the original behavior, no control over any individual
        value's connection count.
      - `min_per_left`/`max_per_left`/`min_per_right`/`max_per_right`:
        control how many times each individual left/right value shows up
        in the join table. Setting any of these switches into
        degree-controlled mode (see `_random_pairs_by_degree`); `join_rows`
        is ignored in that case.

    Returns (join_table_name, join_table_columns) so the caller can write
    it out as its own CSV alongside the other tables.
    """
    left_table, left_field = rel["left"]["table"], rel["left"]["field"]
    right_table, right_field = rel["right"]["table"], rel["right"]["field"]

    left_values = tables[left_table][left_field]
    right_values = tables[right_table][right_field]

    join_table_name = rel.get("join_table", f"{left_table}_{right_table}")
    unique_pairs = rel.get("unique_pairs", True)
    exclude_self = rel.get("exclude_self", False)

    left_col = rel.get("left_as", f"{left_table}_{left_field}")
    right_col = rel.get("right_as", f"{right_table}_{right_field}")
    extra_field_specs: dict = rel.get("fields", {}) or {}

    min_per_left = rel.get("min_per_left")
    max_per_left = rel.get("max_per_left")
    min_per_right = rel.get("min_per_right")
    max_per_right = rel.get("max_per_right")
    degree_controlled = any(
        v is not None
        for v in (min_per_left, max_per_left, min_per_right, max_per_right)
    )

    if degree_controlled:
        edges = _random_pairs_by_degree(
            left_values, right_values,
            min_per_left, max_per_left, min_per_right, max_per_right,
            unique_pairs, exclude_self, join_table_name, rng,
        )
    else:
        default_join_rows = max(len(left_values), len(right_values))
        join_rows = int(rel.get("join_rows", default_join_rows))
        edges = _random_pairs_by_count(
            left_values, right_values, join_rows,
            unique_pairs, exclude_self, join_table_name, rng,
        )

    left_out: list[Any] = []
    right_out: list[Any] = []
    extra_columns: dict[str, list] = {name: [] for name in extra_field_specs}
    extra_used_values: dict[str, set] = {
        name: set()
        for name, spec in extra_field_specs.items()
        if spec.get("unique", False)
    }

    for left_val, right_val in edges:
        row: dict = {left_col: left_val, right_col: right_val}
        for field_name, field_spec in extra_field_specs.items():
            used_values = extra_used_values.get(field_name, set())
            value = generate_field_value(
                field_name, field_spec, rng, used_values, row
            )
            row[field_name] = value

        left_out.append(left_val)
        right_out.append(right_val)
        for field_name in extra_field_specs:
            extra_columns[field_name].append(row[field_name])

    columns = {left_col: left_out, right_col: right_out}
    columns.update(extra_columns)
    return join_table_name, columns


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
