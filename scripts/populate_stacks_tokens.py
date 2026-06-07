#!/usr/bin/env python3
"""Script to populate the packaged global database with curated Stacks tokens.

This script adds Stacks tokens to rotkehlchen/data/global.db so that new installs
have the tokens available without needing a migration.

Usage:
    python scripts/populate_stacks_tokens.py
"""

import csv
import sqlite3
import sys
from pathlib import Path

# Add the project root to the path so we can import rotkehlchen modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rotkehlchen.assets.types import AssetType  # noqa: E402
from rotkehlchen.types import TokenKind  # noqa: E402


def load_tokens_from_csv() -> list[dict[str, str]]:
    """Load token data from CSV file."""
    csv_path = project_root / 'rotkehlchen' / 'data' / 'stacks_tokens_data.csv'
    if not csv_path.exists():
        print(f'Error: CSV file not found at {csv_path}')
        sys.exit(1)

    with csv_path.open(encoding='utf-8') as f:
        return list(csv.DictReader(f))


def populate_stacks_tokens(db_path: Path, tokens: list[dict[str, str]]) -> int:
    """Populate the database with curated Stacks tokens.

    Returns the number of tokens added.
    """
    stacks_type_char = AssetType.STACKS_TOKEN.serialize_for_db()
    token_kind_char = TokenKind.SIP010_FUNGIBLE.serialize_for_db()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    added_count = 0

    for row in tokens:
        contract_id = row['contract_id']
        # CAIP-19: stacks:1/sip010:{address}.{contract}.{asset_name}
        identifier = f'stacks:1/sip010:{contract_id}.{row["token_name"]}'

        # Check if token already exists
        cursor.execute('SELECT 1 FROM assets WHERE identifier = ?', (identifier,))
        if cursor.fetchone() is not None:
            print(f'  Skipping {row["symbol"]} (already exists)')
            continue

        # Insert into assets table
        cursor.execute(
            'INSERT INTO assets (identifier, type, name) VALUES (?, ?, ?)',
            (identifier, stacks_type_char, row['name']),
        )

        # Insert into common_asset_details table
        cursor.execute(
            'INSERT INTO common_asset_details '
            '(identifier, symbol, coingecko, cryptocompare) VALUES (?, ?, ?, ?)',
            (identifier, row['symbol'], row['coingecko'] or None, row['cryptocompare'] or None),
        )

        # Insert into stacks_tokens table
        cursor.execute(
            'INSERT INTO stacks_tokens '
            '(identifier, token_kind, contract_id, decimals, protocol) VALUES (?, ?, ?, ?, ?)',
            (
                identifier,
                token_kind_char,
                contract_id,
                int(row['decimals']) if row['decimals'] else None,
                row['protocol'] or None,
            ),
        )

        added_count += 1
        print(f'  Added {row["symbol"]} ({contract_id})')

    conn.commit()
    conn.close()

    return added_count


def main() -> None:
    packaged_db_path = project_root / 'rotkehlchen' / 'data' / 'global.db'

    if not packaged_db_path.exists():
        print(f'Error: Packaged database not found at {packaged_db_path}')
        sys.exit(1)

    tokens = load_tokens_from_csv()

    print(f'Populating Stacks tokens in {packaged_db_path}')
    print(f'Total curated tokens in CSV: {len(tokens)}')
    print()

    added = populate_stacks_tokens(packaged_db_path, tokens)

    print()
    print(f'Done! Added {added} new Stacks tokens.')

    # Verify
    conn = sqlite3.connect(packaged_db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM stacks_tokens')
    total = cursor.fetchone()[0]
    conn.close()

    print(f'Total Stacks tokens in database: {total}')


if __name__ == '__main__':
    main()
