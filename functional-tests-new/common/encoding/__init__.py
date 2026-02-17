"""
Encoding utilities for OL transaction construction.

This module provides Python implementations of encoding formats used by the
Strata protocol for constructing transactions that can be submitted to the OL.
"""

from .msg_fmt import encode_msg_type, encode_owned_msg
from .ssz import (
    SSZ_MAX_EXTRA_DATA_BYTES,
    SSZ_MAX_LEDGER_REFS,
    SSZ_MAX_MESSAGES,
    SSZ_MAX_PROCESSED_MESSAGES,
    SSZ_MAX_TRANSFERS,
    # Dataclasses
    AccumulatorClaim,
    LedgerRefs,
    MessageEntry,
    MsgPayload,
    OutputMessage,
    OutputTransfer,
    ProofState,
    UpdateInputData,
    UpdateOperationData,
    UpdateOutputs,
    UpdateStateData,
    # Encoding functions
    encode_accumulator_claim,
    encode_ledger_refs,
    encode_message_entry,
    encode_msg_payload,
    encode_output_message,
    encode_proof_state,
    encode_update_input_data,
    encode_update_operation_data,
    encode_update_outputs,
    encode_update_state_data,
)
from .strata_codec import (
    encode_u32,
    encode_u64,
    encode_varint,
    encode_varvec,
    encode_withdrawal_msg_data,
)

__all__ = [
    # strata_codec
    "encode_varint",
    "encode_varvec",
    "encode_u32",
    "encode_u64",
    "encode_withdrawal_msg_data",
    # msg_fmt
    "encode_msg_type",
    "encode_owned_msg",
    # ssz dataclasses
    "AccumulatorClaim",
    "LedgerRefs",
    "MessageEntry",
    "MsgPayload",
    "OutputMessage",
    "OutputTransfer",
    "ProofState",
    "UpdateInputData",
    "UpdateOperationData",
    "UpdateOutputs",
    "UpdateStateData",
    # ssz encoding functions
    "encode_accumulator_claim",
    "encode_msg_payload",
    "encode_output_message",
    "encode_update_outputs",
    "encode_proof_state",
    "encode_update_state_data",
    "encode_message_entry",
    "encode_update_input_data",
    "encode_ledger_refs",
    "encode_update_operation_data",
    # ssz constants
    "SSZ_MAX_PROCESSED_MESSAGES",
    "SSZ_MAX_LEDGER_REFS",
    "SSZ_MAX_EXTRA_DATA_BYTES",
    "SSZ_MAX_TRANSFERS",
    "SSZ_MAX_MESSAGES",
]
