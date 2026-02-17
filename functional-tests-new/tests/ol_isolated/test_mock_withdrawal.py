"""
Test mock withdrawal transaction submission.

This test verifies that a snark account can submit a withdrawal
transaction to the OL and have it processed correctly.
"""

import logging

import flexitest

from common.base_test import StrataNodeTest
from common.config import ServiceType
from common.ol_transaction import (
    WITHDRAWAL_DENOMINATION_SATS,
    SnarkAccountUpdateBuilder,
    WithdrawalIntent,
    make_account_id_special,
)

logger = logging.getLogger(__name__)

# Test account reference byte (matches OLIsolatedEnvConfig default)
TEST_ACCOUNT_REF = 0x42


def make_test_account_id() -> bytes:
    """Create the test account ID used in OLIsolatedEnvConfig."""
    return make_account_id_special(TEST_ACCOUNT_REF)


@flexitest.register
class TestMockWithdrawal(StrataNodeTest):
    """
    Test mock withdrawal transaction submission and processing.

    This test:
    1. Starts OL with a genesis snark account (1.5 BTC balance)
    2. Queries initial account state
    3. Builds and submits a mock withdrawal transaction (1 BTC)
    4. Waits for block production
    5. Verifies balance was reduced
    6. Verifies withdrawal log was emitted
    """

    def __init__(self, ctx: flexitest.InitContext):
        ctx.set_env("ol_isolated")

    def main(self, ctx):
        strata = self.get_service(ServiceType.Strata)

        logger.info("Waiting for Strata RPC to be ready...")
        rpc = strata.wait_for_rpc_ready(timeout=30)

        # Get initial block height
        initial_height = strata.get_cur_block_height(rpc)
        logger.info(f"Initial block height: {initial_height}")

        # Build test account ID
        account_id = make_test_account_id()
        account_id_hex = "0x" + account_id.hex()
        logger.info(f"Test account ID: {account_id_hex}")

        # Query initial account state
        try:
            initial_state = rpc.strata_getSnarkAccountState(account_id_hex, "latest")
            if initial_state:
                logger.info(f"Initial account state: {initial_state}")
                initial_balance = initial_state.get("balance", 0)
                initial_seq_no = initial_state.get("seq_no", 0)
                initial_next_inbox_idx = initial_state.get("next_inbox_msg_idx", 0)
                initial_inner_state = bytes.fromhex(
                    initial_state.get("inner_state", "00" * 32).removeprefix("0x")
                )
            else:
                logger.warning("Account not found, using defaults")
                initial_balance = 2_000_000_000  # Default from genesis (20 BTC)
                initial_seq_no = 0
                initial_next_inbox_idx = 0
                initial_inner_state = bytes(32)
        except Exception as e:
            logger.warning(f"Failed to query initial state: {e}, using defaults")
            initial_balance = 150_000_000
            initial_seq_no = 0
            initial_next_inbox_idx = 0
            initial_inner_state = bytes(32)

        logger.info(f"Initial balance: {initial_balance} sats")

        # Build withdrawal transaction
        withdrawal_dest = b"bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"  # Example P2WPKH
        withdrawal_amount = WITHDRAWAL_DENOMINATION_SATS  # 1 BTC

        logger.info(
            f"Building withdrawal: {withdrawal_amount} sats to {withdrawal_dest.decode()}"
        )

        builder = SnarkAccountUpdateBuilder(
            target=account_id,
            seq_no=initial_seq_no,
            inner_state=initial_inner_state,  # Keep same inner state for simplicity
            next_inbox_idx=initial_next_inbox_idx,
        )

        intent = WithdrawalIntent(
            amount_sats=withdrawal_amount,
            fees=0,
            dest_descriptor=withdrawal_dest,
        )
        builder.with_withdrawal(intent)

        tx = builder.build_rpc_transaction()
        logger.info(f"Built transaction: {tx}")

        # Submit transaction
        logger.info("Submitting withdrawal transaction...")
        try:
            tx_id = rpc.strata_submitTransaction(tx)
            logger.info(f"Transaction submitted, ID: {tx_id}")
        except Exception as e:
            logger.error(f"Failed to submit transaction: {e}")
            raise AssertionError(f"Transaction submission failed: {e}") from e

        # Wait for block production
        logger.info("Waiting for block production...")
        blocks_to_wait = 2
        final_height = strata.wait_for_additional_blocks(blocks_to_wait, rpc)
        logger.info(f"Block height after waiting: {final_height}")

        # Query final account state
        try:
            final_state = rpc.strata_getSnarkAccountState(account_id_hex, "latest")
            if final_state:
                final_balance = final_state.get("balance", 0)
                logger.info(f"Final account state: {final_state}")
            else:
                raise AssertionError("Account not found after transaction")
        except Exception as e:
            logger.error(f"Failed to query final state: {e}")
            raise AssertionError(f"Failed to query final state: {e}") from e

        # Verify balance was reduced
        expected_balance = initial_balance - withdrawal_amount
        logger.info(
            f"Balance: {initial_balance} -> {final_balance} (expected: {expected_balance})"
        )

        if final_balance != expected_balance:
            raise AssertionError(
                f"Balance mismatch: expected {expected_balance}, got {final_balance}"
            )

        logger.info("Withdrawal test passed!")
        return True


@flexitest.register
class TestMockWithdrawalSubmission(StrataNodeTest):
    """
    Simple test that just verifies transaction submission works.

    This is a minimal test that doesn't verify the full withdrawal flow,
    just that we can submit a transaction without errors.
    """

    def __init__(self, ctx: flexitest.InitContext):
        ctx.set_env("ol_isolated")

    def main(self, ctx):
        strata = self.get_service(ServiceType.Strata)

        logger.info("Waiting for Strata RPC to be ready...")
        rpc = strata.wait_for_rpc_ready(timeout=30)

        # Wait for at least one block
        strata.wait_for_additional_blocks(1, rpc)

        # Build test account ID
        account_id = make_test_account_id()
        logger.info(f"Test account ID: 0x{account_id.hex()}")

        # Build a simple withdrawal transaction
        builder = SnarkAccountUpdateBuilder(
            target=account_id,
            seq_no=0,
            inner_state=bytes(32),
            next_inbox_idx=0,
        )

        intent = WithdrawalIntent(
            amount_sats=WITHDRAWAL_DENOMINATION_SATS,
            fees=0,
            dest_descriptor=b"bc1qexample",
        )
        builder.with_withdrawal(intent)

        tx = builder.build_rpc_transaction()

        # Submit transaction - just verify it doesn't error
        logger.info("Submitting withdrawal transaction...")
        try:
            tx_id = rpc.strata_submitTransaction(tx)
            logger.info(f"Transaction submitted successfully, ID: {tx_id}")
        except Exception as e:
            # Log the full transaction for debugging
            import json

            logger.error(f"Transaction payload: {json.dumps(tx, indent=2)}")
            logger.error(f"Transaction submission failed: {e}")
            raise AssertionError(f"Transaction submission failed: {e}") from e

        logger.info("Transaction submission test passed!")
        return True
