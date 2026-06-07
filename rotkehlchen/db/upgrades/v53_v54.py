"""Database upgrade from v53 to v54.

This upgrade adds Stacks blockchain support tables.
"""
import logging
from typing import TYPE_CHECKING, Final

from rotkehlchen.logging import RotkehlchenLogsAdapter, enter_exit_debug_log
from rotkehlchen.utils.progress import perform_userdb_upgrade_steps, progress_step

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.db.drivers.gevent import DBCursor
    from rotkehlchen.db.upgrade_manager import DBUpgradeProgressHandler

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

OLD_FORK_STACKS_LOCATION: Final = 'y'
STACKS_LOCATION: Final = '|'
HYPERLIQUID_LOCATION: Final = 'y'
MONAD_LOCATION: Final = 'z'
GATE_LOCATION: Final = '{'


def _table_exists(cursor: 'DBCursor', table_name: str) -> bool:
    return cursor.execute(
        'SELECT COUNT(*) FROM sqlite_master WHERE type=? AND name=?',
        ('table', table_name),
    ).fetchone()[0] != 0


def _location_exists(cursor: 'DBCursor', location: str) -> bool:
    return cursor.execute(
        'SELECT COUNT(*) FROM location WHERE location=?',
        (location,),
    ).fetchone()[0] != 0


def _iter_tables_with_location_column(cursor: 'DBCursor') -> list[str]:
    table_names = [
        row[0] for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        )
    ]
    return [
        table_name for table_name in table_names
        if table_name != 'location' and any(
            row[1] == 'location'
            for row in cursor.execute(f'PRAGMA table_info("{table_name}")')
        )
    ]


@enter_exit_debug_log(name='UserDB v53->v54 upgrade')
def upgrade_v53_to_v54(db: 'DBHandler', progress_handler: 'DBUpgradeProgressHandler') -> None:
    """Upgrades the DB from v53 to v54. This adds Stacks blockchain support."""

    @progress_step(description='Moving old fork Stacks location data.')
    def _move_old_fork_stacks_location(write_cursor: 'DBCursor') -> None:
        """Move Stacks rows from the old fork location slot before upstream reuses it.

        The fork originally shipped Stacks as location char 'y' / seq 57. Upstream later
        used that slot for Hyperliquid, so old fork databases need their Stacks rows moved
        to the renumbered location '|' / seq 60 before the new enum mapping is used.
        """
        if (
            _table_exists(write_cursor, 'stacks_transactions') is False or
            _location_exists(write_cursor, OLD_FORK_STACKS_LOCATION) is False or
            _location_exists(write_cursor, STACKS_LOCATION) is True
        ):
            return

        write_cursor.execute(
            'INSERT OR IGNORE INTO location(location, seq) VALUES (?, ?)',
            (STACKS_LOCATION, 60),
        )

        moved_rows = 0
        for table_name in _iter_tables_with_location_column(write_cursor):
            write_cursor.execute(
                f'UPDATE "{table_name}" SET location=? WHERE location=?',
                (STACKS_LOCATION, OLD_FORK_STACKS_LOCATION),
            )
            moved_rows += write_cursor.rowcount

        log.info(f'Moved {moved_rows} old fork Stacks location rows to the new slot')

    @progress_step(description='Adding new chain locations to the DB.')
    def _add_chain_locations(write_cursor: 'DBCursor') -> None:
        write_cursor.executemany(
            'INSERT OR IGNORE INTO location(location, seq) VALUES (?, ?)',
            (
                (HYPERLIQUID_LOCATION, 57),
                (MONAD_LOCATION, 58),
                (GATE_LOCATION, 59),
                (STACKS_LOCATION, 60),
            ),
        )

    @progress_step(description='Creating Stacks transaction tables.')
    def _create_stacks_tables(write_cursor: 'DBCursor') -> None:
        """Create the Stacks blockchain tables."""
        write_cursor.executescript("""
        CREATE TABLE IF NOT EXISTS stacks_transactions (
            identifier INTEGER PRIMARY KEY NOT NULL,
            tx_id TEXT NOT NULL UNIQUE,
            block_height INTEGER NOT NULL,
            block_time INTEGER NOT NULL,
            tx_type TEXT NOT NULL,
            sender_address TEXT NOT NULL,
            fee_rate TEXT NOT NULL,
            nonce INTEGER NOT NULL,
            tx_status TEXT NOT NULL,
            recipient_address TEXT,
            amount TEXT,
            contract_id TEXT,
            function_name TEXT,
            function_args TEXT,
            arg_amount_ustx TEXT,
            arg_recipient TEXT,
            arg_delegate_to TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_stacks_tx_contract_function
            ON stacks_transactions(contract_id, function_name);
        CREATE INDEX IF NOT EXISTS idx_stacks_tx_arg_amount
            ON stacks_transactions(arg_amount_ustx) WHERE arg_amount_ustx IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_stacks_tx_arg_recipient
            ON stacks_transactions(arg_recipient) WHERE arg_recipient IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_stacks_tx_arg_delegate
            ON stacks_transactions(arg_delegate_to) WHERE arg_delegate_to IS NOT NULL;

        CREATE TABLE IF NOT EXISTS stackstx_address_mappings (
            tx_id INTEGER NOT NULL,
            address TEXT NOT NULL,
            PRIMARY KEY(tx_id, address),
            FOREIGN KEY(tx_id) REFERENCES stacks_transactions(identifier)
                ON DELETE CASCADE ON UPDATE CASCADE
        );

        CREATE TABLE IF NOT EXISTS stacks_tx_mappings (
            tx_id INTEGER NOT NULL,
            value INTEGER NOT NULL,
            FOREIGN KEY(tx_id) REFERENCES stacks_transactions(identifier)
                ON UPDATE CASCADE ON DELETE CASCADE,
            PRIMARY KEY (tx_id, value)
        );
        """)

    perform_userdb_upgrade_steps(db=db, progress_handler=progress_handler, should_vacuum=False)
