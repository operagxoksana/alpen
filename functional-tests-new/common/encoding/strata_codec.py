"""
Strata codec encoding utilities.

Implements encoding functions compatible with the Rust strata-codec crate.
The encoding uses little-endian byte order for all integer types.
"""

from typing import Union


def encode_varint(n: int) -> bytes:
    """
    Encode an unsigned integer as a LEB128 varint.

    This matches the strata-codec VarVec length prefix encoding.

    Args:
        n: Non-negative integer to encode.

    Returns:
        Varint-encoded bytes.

    Raises:
        ValueError: If n is negative.
    """
    if n < 0:
        raise ValueError(f"Cannot encode negative integer as varint: {n}")

    result = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n != 0:
            byte |= 0x80
        result.append(byte)
        if n == 0:
            break
    return bytes(result)


def encode_varvec(data: Union[bytes, bytearray]) -> bytes:
    """
    Encode a variable-length byte vector with varint length prefix.

    This matches the Rust VarVec<u8> encoding:
    - First: varint-encoded length
    - Then: raw bytes

    Args:
        data: Bytes to encode.

    Returns:
        Length-prefixed encoded bytes.
    """
    length_prefix = encode_varint(len(data))
    return length_prefix + bytes(data)


def encode_u32(value: int) -> bytes:
    """
    Encode a u32 as 4 bytes in little-endian order.

    Args:
        value: Integer in range [0, 2^32 - 1].

    Returns:
        4 bytes in little-endian order.

    Raises:
        ValueError: If value is out of u32 range.
    """
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(f"Value {value} out of u32 range")
    return value.to_bytes(4, "little")


def encode_u64(value: int) -> bytes:
    """
    Encode a u64 as 8 bytes in little-endian order.

    Args:
        value: Integer in range [0, 2^64 - 1].

    Returns:
        8 bytes in little-endian order.

    Raises:
        ValueError: If value is out of u64 range.
    """
    if value < 0 or value > 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"Value {value} out of u64 range")
    return value.to_bytes(8, "little")


# Maximum withdrawal destination descriptor length (from withdrawal.rs)
MAX_WITHDRAWAL_DESC_LEN = 255


def encode_withdrawal_msg_data(fees: int, dest_desc: bytes) -> bytes:
    """
    Encode WithdrawalMsgData as per strata-codec.

    Structure (in encoding order):
    - fees: u32 (4 bytes, little-endian)
    - dest_desc: VarVec<u8> (varint length + bytes)

    Args:
        fees: Operator fees in satoshis (currently ignored by protocol).
        dest_desc: Bitcoin output script descriptor bytes.

    Returns:
        Encoded WithdrawalMsgData.

    Raises:
        ValueError: If fees is out of u32 range or dest_desc exceeds max length.
    """
    if len(dest_desc) > MAX_WITHDRAWAL_DESC_LEN:
        raise ValueError(
            f"Destination descriptor length {len(dest_desc)} exceeds "
            f"maximum {MAX_WITHDRAWAL_DESC_LEN}"
        )

    encoded_fees = encode_u32(fees)
    encoded_dest_desc = encode_varvec(dest_desc)

    return encoded_fees + encoded_dest_desc
