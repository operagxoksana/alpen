"""
Unit tests for encoding utilities.

These tests verify that the Python encoding implementations match
the expected Rust encodings based on test vectors from the Rust codebase.
"""

import unittest


class TestMsgFmtEncoding(unittest.TestCase):
    """Test SPS-msg-fmt type ID encoding."""

    def test_single_byte_type_ids(self):
        """Type IDs 0x00-0x7F encode as single byte."""
        from common.encoding import encode_msg_type

        # From msg.rs test: type 0x00 body "hello" -> 0x00...
        self.assertEqual(encode_msg_type(0x00), bytes([0x00]))
        self.assertEqual(encode_msg_type(0x03), bytes([0x03]))  # WITHDRAWAL_MSG_TYPE_ID
        self.assertEqual(encode_msg_type(0x7F), bytes([0x7F]))

    def test_two_byte_type_ids(self):
        """Type IDs 0x80+ encode as multiple bytes."""
        from common.encoding import encode_msg_type

        # From msg.rs test: type 0x80 body "abc" -> [0x80, 0x80, ...]
        self.assertEqual(encode_msg_type(0x80), bytes([0x80, 0x80]))

        # From msg.rs test: type 0x1234 body "xyz" -> [0x92, 0x34, ...]
        self.assertEqual(encode_msg_type(0x1234), bytes([0x92, 0x34]))

    def test_owned_msg_encoding(self):
        """Test complete OwnedMsg encoding (type + body)."""
        from common.encoding import encode_owned_msg

        # type 0x00 body "hello" -> [0x00, 'h', 'e', 'l', 'l', 'o']
        result = encode_owned_msg(0x00, b"hello")
        self.assertEqual(result, bytes([0x00, 0x68, 0x65, 0x6C, 0x6C, 0x6F]))

        # type 0x80 body "abc" -> [0x80, 0x80, 'a', 'b', 'c']
        result = encode_owned_msg(0x80, b"abc")
        self.assertEqual(result, bytes([0x80, 0x80, 0x61, 0x62, 0x63]))

        # type 0x1234 body "xyz" -> [0x92, 0x34, 'x', 'y', 'z']
        result = encode_owned_msg(0x1234, b"xyz")
        self.assertEqual(result, bytes([0x92, 0x34, 0x78, 0x79, 0x7A]))


class TestStrataCodec(unittest.TestCase):
    """Test strata-codec encoding functions."""

    def test_varint_encoding(self):
        """Test LEB128 varint encoding."""
        from common.encoding import encode_varint

        # Single byte values
        self.assertEqual(encode_varint(0), bytes([0x00]))
        self.assertEqual(encode_varint(1), bytes([0x01]))
        self.assertEqual(encode_varint(127), bytes([0x7F]))

        # Two byte values
        self.assertEqual(encode_varint(128), bytes([0x80, 0x01]))
        self.assertEqual(encode_varint(255), bytes([0xFF, 0x01]))
        self.assertEqual(encode_varint(300), bytes([0xAC, 0x02]))

    def test_u32_encoding(self):
        """Test u32 little-endian encoding."""
        from common.encoding import encode_u32

        self.assertEqual(encode_u32(0), bytes([0x00, 0x00, 0x00, 0x00]))
        self.assertEqual(encode_u32(1), bytes([0x01, 0x00, 0x00, 0x00]))
        self.assertEqual(encode_u32(0x12345678), bytes([0x78, 0x56, 0x34, 0x12]))

    def test_u64_encoding(self):
        """Test u64 little-endian encoding."""
        from common.encoding import encode_u64

        self.assertEqual(
            encode_u64(0), bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        )
        self.assertEqual(
            encode_u64(100_000_000),  # 1 BTC in sats
            bytes([0x00, 0xE1, 0xF5, 0x05, 0x00, 0x00, 0x00, 0x00]),
        )

    def test_varvec_encoding(self):
        """Test VarVec<u8> encoding (varint length + bytes)."""
        from common.encoding import encode_varvec

        # Empty
        self.assertEqual(encode_varvec(b""), bytes([0x00]))

        # Short data
        self.assertEqual(encode_varvec(b"abc"), bytes([0x03, 0x61, 0x62, 0x63]))

        # Longer data
        data = b"bc1qexample"
        result = encode_varvec(data)
        self.assertEqual(result[0], len(data))  # Length prefix
        self.assertEqual(result[1:], data)  # Raw bytes

    def test_withdrawal_msg_data_encoding(self):
        """Test WithdrawalMsgData encoding."""
        from common.encoding import encode_withdrawal_msg_data

        # fees=0, dest_desc=b"bc1qexample"
        result = encode_withdrawal_msg_data(0, b"bc1qexample")

        # Should be: u32(0) + varvec(b"bc1qexample")
        # u32(0) = [0, 0, 0, 0]
        # varvec(b"bc1qexample") = [11] + b"bc1qexample"
        expected_fees = bytes([0x00, 0x00, 0x00, 0x00])
        expected_desc = bytes([11]) + b"bc1qexample"
        self.assertEqual(result, expected_fees + expected_desc)


class TestSSZEncoding(unittest.TestCase):
    """Test minimal SSZ encoding."""

    def test_proof_state_encoding(self):
        """Test ProofState SSZ encoding (fixed-size container)."""
        from common.encoding import ProofState, encode_proof_state

        state = ProofState(inner_state=bytes(32), next_inbox_msg_idx=0)
        result = encode_proof_state(state)

        # inner_state (32 bytes) + next_inbox_msg_idx (8 bytes) = 40 bytes
        self.assertEqual(len(result), 40)
        self.assertEqual(result[:32], bytes(32))  # inner_state
        self.assertEqual(result[32:], bytes(8))  # u64(0)

    def test_msg_payload_encoding(self):
        """Test MsgPayload SSZ encoding (container with variable field)."""
        from common.encoding import MsgPayload, encode_msg_payload

        payload = MsgPayload(value=100_000_000, data=b"test")
        result = encode_msg_payload(payload)

        # Fixed part: value (8 bytes) + offset (4 bytes) = 12 bytes
        # Variable part: data (4 bytes)
        # Total: 16 bytes
        self.assertEqual(len(result), 16)

        # First 8 bytes should be value (100M in little-endian)
        value_bytes = result[:8]
        self.assertEqual(int.from_bytes(value_bytes, "little"), 100_000_000)

        # Next 4 bytes should be offset (12 = size of fixed part)
        offset_bytes = result[8:12]
        self.assertEqual(int.from_bytes(offset_bytes, "little"), 12)

        # Last 4 bytes should be the data
        self.assertEqual(result[12:], b"test")

    def test_update_outputs_empty(self):
        """Test UpdateOutputs SSZ encoding with empty lists."""
        from common.encoding import UpdateOutputs, encode_update_outputs

        outputs = UpdateOutputs(transfers=[], messages=[])
        result = encode_update_outputs(outputs)

        # Two offsets (4 bytes each) pointing to empty lists
        # offset[0] = 8, offset[1] = 8 (both point to same place, both lists empty)
        self.assertEqual(len(result), 8)

    def test_ledger_refs_empty(self):
        """Test LedgerRefs SSZ encoding with empty list."""
        from common.encoding import LedgerRefs, encode_ledger_refs

        refs = LedgerRefs(l1_header_refs=[])
        result = encode_ledger_refs(refs)

        # Single offset (4 bytes) pointing to empty list
        self.assertEqual(len(result), 4)


class TestTransactionBuilder(unittest.TestCase):
    """Test the transaction builder."""

    def test_build_withdrawal_transaction(self):
        """Test building a complete withdrawal transaction."""
        from common.ol_transaction import (
            BRIDGE_GATEWAY_ACCT_ID,
            WITHDRAWAL_DENOMINATION_SATS,
            SnarkAccountUpdateBuilder,
            WithdrawalIntent,
        )

        account_id = bytes(31) + bytes([0x42])  # Test account
        builder = SnarkAccountUpdateBuilder(
            target=account_id,
            seq_no=0,
            inner_state=bytes(32),
            next_inbox_idx=0,
        )

        intent = WithdrawalIntent(
            amount_sats=WITHDRAWAL_DENOMINATION_SATS,
            fees=0,
            dest_descriptor=b"bc1qtest",
        )
        builder.with_withdrawal(intent)

        tx = builder.build_rpc_transaction()

        # Verify structure
        self.assertIn("payload", tx)
        self.assertIn("attachments", tx)
        self.assertEqual(tx["payload"]["type"], "snark_account_update")
        self.assertEqual(tx["payload"]["target"], "0x" + account_id.hex())
        self.assertTrue(tx["payload"]["update_operation_encoded"].startswith("0x"))
        self.assertEqual(tx["payload"]["update_proof"], "0x")
        self.assertIsNone(tx["attachments"]["min_slot"])
        self.assertIsNone(tx["attachments"]["max_slot"])

    def test_bridge_gateway_account_id(self):
        """Test that bridge gateway account ID is correct."""
        from common.ol_transaction import BRIDGE_GATEWAY_ACCT_ID

        # AccountId::special(0x10) = 31 zeros + 0x10
        expected = bytes(31) + bytes([0x10])
        self.assertEqual(BRIDGE_GATEWAY_ACCT_ID, expected)


if __name__ == "__main__":
    unittest.main()
