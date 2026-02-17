"""
OL Transaction builder for functional tests.

Provides utilities to construct snark account update transactions
that can be submitted to the OL via RPC.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .encoding import (
    MsgPayload,
    OutputMessage,
    ProofState,
    UpdateInputData,
    UpdateOperationData,
    UpdateOutputs,
    UpdateStateData,
    LedgerRefs,
    encode_owned_msg,
    encode_update_operation_data,
    encode_withdrawal_msg_data,
)

# Bridge gateway account ID: AccountId::special(0x10)
# This is a 32-byte array with 0x10 in the last byte, all other bytes zero.
BRIDGE_GATEWAY_ACCT_ID = bytes(31) + bytes([0x10])

# Message type IDs from withdrawal.rs
WITHDRAWAL_MSG_TYPE_ID = 0x03
DEPOSIT_MSG_TYPE_ID = 0x02

# Standard withdrawal denomination (1 BTC in satoshis)
WITHDRAWAL_DENOMINATION_SATS = 100_000_000


def make_account_id_special(ref_byte: int) -> bytes:
    """
    Create a special account ID with the given reference byte.

    Special account IDs have all bytes zero except the last byte.
    This matches AccountId::special(ref_byte) in Rust.

    Args:
        ref_byte: The reference byte (0-255).

    Returns:
        32-byte account ID.
    """
    return bytes(31) + bytes([ref_byte])


@dataclass
class WithdrawalIntent:
    """
    Describes a withdrawal from a snark account to L1 Bitcoin.

    The amount must be the standard withdrawal denomination (1 BTC).
    """

    amount_sats: int = WITHDRAWAL_DENOMINATION_SATS
    fees: int = 0  # Operator fees (currently ignored by protocol)
    dest_descriptor: bytes = field(default_factory=lambda: b"bc1qexample")

    def __post_init__(self):
        if self.amount_sats != WITHDRAWAL_DENOMINATION_SATS:
            # For now, warn but allow - protocol may have flexibility
            pass


@dataclass
class SnarkAccountUpdateBuilder:
    """
    Builder for snark account update transactions.

    Usage:
        builder = SnarkAccountUpdateBuilder(
            target=account_id,
            seq_no=0,
            inner_state=bytes(32),
            next_inbox_idx=0,
        )
        builder.with_withdrawal(WithdrawalIntent())
        tx = builder.build_rpc_transaction()
        rpc.strata_submitTransaction(tx)
    """

    # Target snark account ID (32 bytes)
    target: bytes

    # Sequence number for this update
    seq_no: int

    # New inner state commitment (32 bytes)
    inner_state: bytes

    # Next inbox message index after processing
    next_inbox_idx: int

    # Output messages to emit
    _output_messages: list[OutputMessage] = field(default_factory=list)

    # Extra data to include in DA
    _extra_data: bytes = field(default=b"")

    def with_withdrawal(self, intent: WithdrawalIntent) -> SnarkAccountUpdateBuilder:
        """
        Add a withdrawal output message.

        This creates an OutputMessage to the bridge gateway account
        with the withdrawal request encoded according to the protocol.

        Args:
            intent: The withdrawal parameters.

        Returns:
            Self for chaining.
        """
        # Step 1: Encode WithdrawalMsgData using strata-codec
        withdrawal_body = encode_withdrawal_msg_data(
            intent.fees, intent.dest_descriptor
        )

        # Step 2: Wrap in OwnedMsg with WITHDRAWAL_MSG_TYPE_ID
        withdrawal_msg_bytes = encode_owned_msg(WITHDRAWAL_MSG_TYPE_ID, withdrawal_body)

        # Step 3: Create MsgPayload with the withdrawal amount
        payload = MsgPayload(value=intent.amount_sats, data=withdrawal_msg_bytes)

        # Step 4: Create OutputMessage to bridge gateway
        output_message = OutputMessage(dest=BRIDGE_GATEWAY_ACCT_ID, payload=payload)

        self._output_messages.append(output_message)
        return self

    def with_extra_data(self, data: bytes) -> SnarkAccountUpdateBuilder:
        """
        Set extra data to include in the DA payload.

        Args:
            data: Arbitrary bytes to persist.

        Returns:
            Self for chaining.
        """
        self._extra_data = data
        return self

    def _build_update_operation_data(self) -> bytes:
        """
        Build and SSZ-encode the UpdateOperationData.

        Returns:
            SSZ-encoded UpdateOperationData bytes.
        """
        # Build proof state
        proof_state = ProofState(
            inner_state=self.inner_state, next_inbox_msg_idx=self.next_inbox_idx
        )

        # Build update state data
        update_state = UpdateStateData(
            proof_state=proof_state, extra_data=self._extra_data
        )

        # Build update input data
        # For mock transactions, we don't process any inbox messages
        input_data = UpdateInputData(
            seq_no=self.seq_no,
            messages=[],  # No processed messages for mock
            update_state=update_state,
        )

        # Build ledger refs (empty for mock)
        ledger_refs = LedgerRefs(l1_header_refs=[])

        # Build outputs
        outputs = UpdateOutputs(
            transfers=[],  # No native transfers
            messages=self._output_messages,
        )

        # Build full operation data
        operation_data = UpdateOperationData(
            input=input_data, ledger_refs=ledger_refs, outputs=outputs
        )

        return encode_update_operation_data(operation_data)

    def build_rpc_transaction(self) -> dict:
        """
        Build the complete RPC transaction payload.

        Returns:
            Dictionary matching the RpcOLTransaction structure for JSON serialization.
        """
        # Encode the update operation data
        update_operation_encoded = self._build_update_operation_data()

        # Build the RPC payload structure
        # This matches RpcOLTransaction from txn.rs
        return {
            "payload": {
                "type": "snark_account_update",
                "target": "0x" + self.target.hex(),
                "update_operation_encoded": "0x" + update_operation_encoded.hex(),
                "update_proof": "0x",  # Empty proof for AlwaysAccept predicate
            },
            "attachments": {
                "min_slot": None,
                "max_slot": None,
            },
        }


def build_mock_withdrawal_transaction(
    target_account: bytes,
    seq_no: int,
    inner_state: bytes,
    next_inbox_idx: int,
    withdrawal_amount: int = WITHDRAWAL_DENOMINATION_SATS,
    withdrawal_dest: bytes = b"bc1qexample",
) -> dict:
    """
    Convenience function to build a mock withdrawal transaction.

    Args:
        target_account: The snark account ID (32 bytes).
        seq_no: Sequence number for this update.
        inner_state: New inner state commitment (32 bytes).
        next_inbox_idx: Next inbox message index after processing.
        withdrawal_amount: Amount to withdraw in satoshis (default 1 BTC).
        withdrawal_dest: Bitcoin output descriptor.

    Returns:
        RPC transaction dictionary ready for submission.
    """
    intent = WithdrawalIntent(
        amount_sats=withdrawal_amount, fees=0, dest_descriptor=withdrawal_dest
    )

    builder = SnarkAccountUpdateBuilder(
        target=target_account,
        seq_no=seq_no,
        inner_state=inner_state,
        next_inbox_idx=next_inbox_idx,
    )
    builder.with_withdrawal(intent)

    return builder.build_rpc_transaction()
