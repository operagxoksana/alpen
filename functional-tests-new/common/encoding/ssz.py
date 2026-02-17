"""
Minimal SSZ encoding for snark account update structures.

This module implements SSZ (Simple Serialize) encoding for the UpdateOperationData
and related structures needed to construct snark account update transactions.

SSZ encoding rules:
- Fixed-size types: encoded directly in little-endian
- Variable-size types: use offset-based encoding
- Containers: fixed parts first (including offsets), then variable parts
- Lists: length implicitly determined by total byte length

Reference: https://ethereum.org/en/developers/docs/data-structures-and-encoding/ssz/
"""

from dataclasses import dataclass

# Constants from update.ssz
SSZ_MAX_PROCESSED_MESSAGES = 2 << 15  # 65536
SSZ_MAX_LEDGER_REFS = 2 << 15  # 65536
SSZ_MAX_EXTRA_DATA_BYTES = 2 << 20  # 2MB
SSZ_MAX_TRANSFERS = 2 << 15  # 65536
SSZ_MAX_MESSAGES = 2 << 15  # 65536
SSZ_MAX_MSG_PAYLOAD_DATA_BYTES = 1 << 20  # 1MB

# SSZ uses 4-byte offsets
BYTES_PER_LENGTH_OFFSET = 4


def _encode_ssz_u32(value: int) -> bytes:
    """Encode u32 as 4 bytes little-endian."""
    return value.to_bytes(4, "little")


def _encode_ssz_u64(value: int) -> bytes:
    """Encode u64 as 8 bytes little-endian."""
    return value.to_bytes(8, "little")


def _encode_ssz_bytes32(data: bytes) -> bytes:
    """Encode a fixed 32-byte array."""
    if len(data) != 32:
        raise ValueError(f"Expected 32 bytes, got {len(data)}")
    return data


def _encode_ssz_list_u8(data: bytes) -> bytes:
    """
    Encode a List[uint8, N] in SSZ.

    For a list of bytes, SSZ simply concatenates them.
    The length is implicit from the container's offset calculation.
    """
    return bytes(data)


def _encode_ssz_container_with_variable_parts(
    fixed_parts: list[bytes],
    variable_parts: list[bytes],
    variable_indices: list[int],
) -> bytes:
    """
    Encode an SSZ container with both fixed and variable parts.

    Args:
        fixed_parts: List of encoded fixed-size fields (in order).
                     For variable-size fields, use empty bytes as placeholder.
        variable_parts: List of encoded variable-size field data.
        variable_indices: Indices in fixed_parts where variable fields are located.

    Returns:
        SSZ-encoded container bytes.
    """
    # Calculate total fixed part size (including 4-byte offsets for variable fields)
    fixed_size = 0
    for i, part in enumerate(fixed_parts):
        if i in variable_indices:
            fixed_size += BYTES_PER_LENGTH_OFFSET  # Offset placeholder
        else:
            fixed_size += len(part)

    # Build the fixed part with offsets
    result = bytearray()
    current_offset = fixed_size  # Variable data starts after all fixed data

    variable_part_idx = 0
    for i, part in enumerate(fixed_parts):
        if i in variable_indices:
            # Write offset to the variable data
            result.extend(_encode_ssz_u32(current_offset))
            current_offset += len(variable_parts[variable_part_idx])
            variable_part_idx += 1
        else:
            result.extend(part)

    # Append variable parts in order
    for var_part in variable_parts:
        result.extend(var_part)

    return bytes(result)


# AccountId is Bytes32
def encode_account_id(account_id: bytes) -> bytes:
    """Encode AccountId (32 bytes)."""
    return _encode_ssz_bytes32(account_id)


# BitcoinAmount is u64
def encode_bitcoin_amount(sats: int) -> bytes:
    """Encode BitcoinAmount (u64, satoshis)."""
    return _encode_ssz_u64(sats)


@dataclass
class MsgPayload:
    """Message payload: value in satoshis + data bytes."""

    value: int  # BitcoinAmount (u64)
    data: bytes  # List[uint8, MAX_MSG_PAYLOAD_DATA_BYTES]


def encode_msg_payload(payload: MsgPayload) -> bytes:
    """
    Encode MsgPayload SSZ container.

    Structure:
    - value: uint64 (8 bytes, fixed)
    - data: List[uint8, MAX] (variable)
    """
    fixed_parts = [
        encode_bitcoin_amount(payload.value),  # value (fixed)
        b"",  # data placeholder (variable)
    ]
    variable_parts = [_encode_ssz_list_u8(payload.data)]
    variable_indices = [1]

    return _encode_ssz_container_with_variable_parts(
        fixed_parts, variable_parts, variable_indices
    )


@dataclass
class OutputMessage:
    """Message sent to an OL account with data payload."""

    dest: bytes  # AccountId (32 bytes)
    payload: MsgPayload


def encode_output_message(msg: OutputMessage) -> bytes:
    """
    Encode OutputMessage SSZ container.

    Structure:
    - dest: AccountId (32 bytes, fixed)
    - payload: MsgPayload (variable - it's a container with variable parts)
    """
    fixed_parts = [
        encode_account_id(msg.dest),  # dest (fixed)
        b"",  # payload placeholder (variable)
    ]
    variable_parts = [encode_msg_payload(msg.payload)]
    variable_indices = [1]

    return _encode_ssz_container_with_variable_parts(
        fixed_parts, variable_parts, variable_indices
    )


@dataclass
class OutputTransfer:
    """Transfer of native asset to an OL account."""

    dest: bytes  # AccountId (32 bytes)
    value: int  # BitcoinAmount (u64)


def encode_output_transfer(transfer: OutputTransfer) -> bytes:
    """
    Encode OutputTransfer SSZ container.

    Structure:
    - dest: AccountId (32 bytes, fixed)
    - value: BitcoinAmount (8 bytes, fixed)

    This is a fixed-size container (no variable parts).
    """
    return encode_account_id(transfer.dest) + encode_bitcoin_amount(transfer.value)


@dataclass
class UpdateOutputs:
    """Collection of outputs from an update."""

    transfers: list[OutputTransfer]
    messages: list[OutputMessage]


def encode_update_outputs(outputs: UpdateOutputs) -> bytes:
    """
    Encode UpdateOutputs SSZ container.

    Structure:
    - transfers: List[OutputTransfer, MAX_TRANSFERS] (variable)
    - messages: List[OutputMessage, MAX_MESSAGES] (variable)

    Both fields are variable-length lists.
    """
    # Encode transfers list
    encoded_transfers = b"".join(
        encode_output_transfer(t) for t in outputs.transfers
    )

    # Encode messages list - each OutputMessage is variable size
    # For a list of variable-size elements, we need offsets
    if outputs.messages:
        encoded_messages = _encode_ssz_list_of_variable_containers(
            [encode_output_message(m) for m in outputs.messages]
        )
    else:
        encoded_messages = b""

    fixed_parts = [
        b"",  # transfers placeholder (variable)
        b"",  # messages placeholder (variable)
    ]
    variable_parts = [encoded_transfers, encoded_messages]
    variable_indices = [0, 1]

    return _encode_ssz_container_with_variable_parts(
        fixed_parts, variable_parts, variable_indices
    )


def _encode_ssz_list_of_variable_containers(encoded_items: list[bytes]) -> bytes:
    """
    Encode a list of variable-size SSZ containers.

    For lists of variable-size elements, SSZ uses:
    - N offsets (4 bytes each) pointing to each element
    - Then the serialized elements concatenated
    """
    if not encoded_items:
        return b""

    n = len(encoded_items)
    # Calculate offset to first element
    offsets_size = n * BYTES_PER_LENGTH_OFFSET

    result = bytearray()

    # Write offsets
    current_offset = offsets_size
    for item in encoded_items:
        result.extend(_encode_ssz_u32(current_offset))
        current_offset += len(item)

    # Write elements
    for item in encoded_items:
        result.extend(item)

    return bytes(result)


@dataclass
class ProofState:
    """Snark account's proof state."""

    inner_state: bytes  # Bytes32 - commitment to internal state
    next_inbox_msg_idx: int  # u64 - next message index to process


def encode_proof_state(state: ProofState) -> bytes:
    """
    Encode ProofState SSZ container.

    Structure:
    - inner_state: Bytes32 (32 bytes, fixed)
    - next_inbox_msg_idx: uint64 (8 bytes, fixed)

    This is a fixed-size container.
    """
    return _encode_ssz_bytes32(state.inner_state) + _encode_ssz_u64(
        state.next_inbox_msg_idx
    )


@dataclass
class UpdateStateData:
    """State update that goes into DA."""

    proof_state: ProofState
    extra_data: bytes  # List[uint8, MAX_EXTRA_DATA_BYTES]


def encode_update_state_data(data: UpdateStateData) -> bytes:
    """
    Encode UpdateStateData SSZ container.

    Structure:
    - proof_state: ProofState (40 bytes, fixed)
    - extra_data: List[uint8, MAX] (variable)
    """
    fixed_parts = [
        encode_proof_state(data.proof_state),  # proof_state (fixed)
        b"",  # extra_data placeholder (variable)
    ]
    variable_parts = [_encode_ssz_list_u8(data.extra_data)]
    variable_indices = [1]

    return _encode_ssz_container_with_variable_parts(
        fixed_parts, variable_parts, variable_indices
    )


@dataclass
class MessageEntry:
    """Entry in a message inbox MMR."""

    source: bytes  # AccountId (32 bytes)
    incl_epoch: int  # u32 - epoch when message was included
    payload: MsgPayload


def encode_message_entry(entry: MessageEntry) -> bytes:
    """
    Encode MessageEntry SSZ container.

    Structure:
    - source: AccountId (32 bytes, fixed)
    - incl_epoch: uint32 (4 bytes, fixed)
    - payload: MsgPayload (variable)
    """
    fixed_parts = [
        encode_account_id(entry.source),  # source (fixed)
        _encode_ssz_u32(entry.incl_epoch),  # incl_epoch (fixed)
        b"",  # payload placeholder (variable)
    ]
    variable_parts = [encode_msg_payload(entry.payload)]
    variable_indices = [2]

    return _encode_ssz_container_with_variable_parts(
        fixed_parts, variable_parts, variable_indices
    )


@dataclass
class UpdateInputData:
    """Input sufficient to perform a state update."""

    seq_no: int  # u64 - sequence number
    messages: list[MessageEntry]  # processed inbox messages
    update_state: UpdateStateData


def encode_update_input_data(data: UpdateInputData) -> bytes:
    """
    Encode UpdateInputData SSZ container.

    Structure:
    - seq_no: uint64 (8 bytes, fixed)
    - messages: List[MessageEntry, MAX] (variable - each entry is variable)
    - update_state: UpdateStateData (variable)
    """
    # Encode messages list (variable-size elements)
    if data.messages:
        encoded_messages = _encode_ssz_list_of_variable_containers(
            [encode_message_entry(m) for m in data.messages]
        )
    else:
        encoded_messages = b""

    fixed_parts = [
        _encode_ssz_u64(data.seq_no),  # seq_no (fixed)
        b"",  # messages placeholder (variable)
        b"",  # update_state placeholder (variable)
    ]
    variable_parts = [encoded_messages, encode_update_state_data(data.update_state)]
    variable_indices = [1, 2]

    return _encode_ssz_container_with_variable_parts(
        fixed_parts, variable_parts, variable_indices
    )


@dataclass
class AccumulatorClaim:
    """Claim about an accumulator entry."""

    leaf_hash: bytes  # Bytes32
    leaf_idx: int  # u64


def encode_accumulator_claim(claim: AccumulatorClaim) -> bytes:
    """Encode AccumulatorClaim (fixed-size container)."""
    return _encode_ssz_bytes32(claim.leaf_hash) + _encode_ssz_u64(claim.leaf_idx)


@dataclass
class LedgerRefs:
    """References to entries in ledger accumulators."""

    l1_header_refs: list[AccumulatorClaim]


def encode_ledger_refs(refs: LedgerRefs) -> bytes:
    """
    Encode LedgerRefs SSZ container.

    Structure:
    - l1_header_refs: List[AccumulatorClaim, MAX_LEDGER_REFS] (variable)

    AccumulatorClaim is fixed-size (32 + 8 = 40 bytes), so the list
    is simply concatenated without internal offsets.
    """
    # List of fixed-size elements - just concatenate
    encoded_refs = b"".join(encode_accumulator_claim(c) for c in refs.l1_header_refs)

    fixed_parts = [
        b"",  # l1_header_refs placeholder (variable)
    ]
    variable_parts = [encoded_refs]
    variable_indices = [0]

    return _encode_ssz_container_with_variable_parts(
        fixed_parts, variable_parts, variable_indices
    )


@dataclass
class UpdateOperationData:
    """Description of the update operation."""

    input: UpdateInputData
    ledger_refs: LedgerRefs
    outputs: UpdateOutputs


def encode_update_operation_data(data: UpdateOperationData) -> bytes:
    """
    Encode UpdateOperationData SSZ container.

    Structure:
    - input: UpdateInputData (variable)
    - ledger_refs: LedgerRefs (variable)
    - outputs: UpdateOutputs (variable)

    All three fields are variable-size.
    """
    fixed_parts = [
        b"",  # input placeholder (variable)
        b"",  # ledger_refs placeholder (variable)
        b"",  # outputs placeholder (variable)
    ]
    variable_parts = [
        encode_update_input_data(data.input),
        encode_ledger_refs(data.ledger_refs),
        encode_update_outputs(data.outputs),
    ]
    variable_indices = [0, 1, 2]

    return _encode_ssz_container_with_variable_parts(
        fixed_parts, variable_parts, variable_indices
    )
