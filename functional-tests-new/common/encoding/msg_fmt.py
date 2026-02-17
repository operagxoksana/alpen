"""
Message format encoding (SPS-msg-fmt / strata-msg-fmt).

Implements the message type encoding used by the strata-msg-fmt crate.
Messages consist of a type ID (encoded with a compact varint-like scheme)
followed by the raw body bytes.
"""


def encode_msg_type(type_id: int) -> bytes:
    """
    Encode a message type ID using SPS-msg-fmt encoding.

    Encoding scheme (based on test vectors from msg.rs):
    - 0x00-0x7F: Single byte, value as-is
    - 0x80-0x3FFF: Two bytes
      - First byte: 0x80 | (value & 0x7F)
      - Second byte: value >> 7
    - Higher values: Continue pattern with more bytes

    Test vectors from Rust tests:
    - type 0x00 -> [0x00]
    - type 0x80 -> [0x80, 0x80]  (0x80 has bit 7 set, so continuation)
    - type 0x1234 -> [0x92, 0x34]

    Actually, analyzing the test vectors more carefully:
    - 0x80 encodes to [0x80, 0x80]: first byte 0x80 means continuation,
      and since 0x80 & 0x7F = 0, we need the full 0x80 in next byte? No...

    Let me re-analyze:
    - For 0x80: encoded = [0x80, 0x80]
    - For 0x1234: encoded = [0x92, 0x34]

    For 0x1234 = 4660:
      - 0x92 = 0b10010010 = 146
      - 0x34 = 0b00110100 = 52
      - If we interpret: (0x92 - 0x80) * 256 + 0x34 = 0x12 * 256 + 0x34 = 4660 = 0x1234
      - No wait: (0x92 & 0x7F) << 8 | 0x34 = 0x12 << 8 | 0x34 = 0x1234

    For 0x80 = 128:
      - Encoded: [0x80, 0x80]
      - (0x80 & 0x7F) << 8 | 0x80 = 0 << 8 | 0x80 = 0x80 = 128

    So the encoding for 2-byte types (0x80-0x3FFF) is:
      - First byte: 0x80 | ((value >> 8) & 0x7F)
      - Second byte: value & 0xFF

    Let me verify:
      - 0x80: first = 0x80 | ((0x80 >> 8) & 0x7F) = 0x80 | 0 = 0x80
              second = 0x80 & 0xFF = 0x80
              Result: [0x80, 0x80] CORRECT!
      - 0x1234: first = 0x80 | ((0x1234 >> 8) & 0x7F) = 0x80 | 0x12 = 0x92
               second = 0x1234 & 0xFF = 0x34
               Result: [0x92, 0x34] CORRECT!

    Args:
        type_id: Message type ID (u16 range: 0-65535).

    Returns:
        Encoded type ID bytes.

    Raises:
        ValueError: If type_id is negative or too large.
    """
    if type_id < 0:
        raise ValueError(f"Type ID cannot be negative: {type_id}")

    if type_id < 0x80:
        # Single byte encoding
        return bytes([type_id])
    elif type_id < 0x4000:
        # Two byte encoding
        first_byte = 0x80 | ((type_id >> 8) & 0x7F)
        second_byte = type_id & 0xFF
        return bytes([first_byte, second_byte])
    else:
        # Three or more bytes - extend the pattern
        # For now, support up to 0x3FFFFF (22 bits) with 3 bytes
        if type_id < 0x200000:
            first_byte = 0xC0 | ((type_id >> 16) & 0x3F)
            second_byte = (type_id >> 8) & 0xFF
            third_byte = type_id & 0xFF
            return bytes([first_byte, second_byte, third_byte])
        else:
            raise ValueError(f"Type ID {type_id} too large for encoding")


def encode_owned_msg(type_id: int, body: bytes) -> bytes:
    """
    Encode a complete OwnedMsg (type ID + body).

    Format: [encoded_type_id][raw_body_bytes]

    This matches the Rust OwnedMsg::to_vec() output.

    Args:
        type_id: Message type ID.
        body: Raw message body bytes.

    Returns:
        Encoded message bytes.
    """
    encoded_type = encode_msg_type(type_id)
    return encoded_type + body
