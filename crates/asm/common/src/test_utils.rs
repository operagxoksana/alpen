//! Test utilities for the asm-common crate.

use bitcoin::{
    Amount, OutPoint, ScriptBuf, Sequence, Transaction, TxIn, TxOut, Witness, XOnlyPublicKey,
    absolute::LockTime,
    key::UntweakedKeypair,
    secp256k1::{SECP256K1, schnorr::Signature},
    taproot::{LeafVersion, TaprootBuilder},
    transaction::Version,
};
use rand::{RngCore, rngs::OsRng};
use strata_l1_envelope_fmt::builder::EnvelopeScriptBuilder;
use strata_l1_txfmt::{MagicBytes, ParseConfig, TagData};

pub const TEST_MAGIC_BYTES: MagicBytes = MagicBytes::new(*b"ALPN");

/// Creates a stub reveal transaction containing the envelope script.
/// This is a simplified implementation for testing purposes.
pub fn create_reveal_transaction_stub(
    envelope_payload: Vec<u8>,
    sps50_tag: TagData,
) -> Transaction {
    // Create commit key
    let mut rand_bytes = [0; 32];
    OsRng.fill_bytes(&mut rand_bytes);
    let key_pair = UntweakedKeypair::from_seckey_slice(SECP256K1, &rand_bytes).unwrap();
    let public_key = XOnlyPublicKey::from_keypair(&key_pair).0;

    // Start creating envelope content
    let reveal_script = EnvelopeScriptBuilder::with_pubkey(&public_key.serialize())
        .unwrap()
        .add_envelope(&envelope_payload)
        .unwrap()
        .build()
        .unwrap();

    // Create spend info for tapscript
    let taproot_spend_info = TaprootBuilder::new()
        .add_leaf(0, reveal_script.clone())
        .unwrap()
        .finalize(SECP256K1, public_key)
        .expect("Could not build taproot spend info");

    let sps50_script = ParseConfig::new(TEST_MAGIC_BYTES)
        .encode_script_buf(&sps50_tag.as_ref())
        .unwrap();

    let signature = Signature::from_slice(&[0u8; 64]).unwrap();
    let mut witness = Witness::new();
    witness.push(signature.as_ref());
    witness.push(reveal_script.clone());
    witness.push(
        taproot_spend_info
            .control_block(&(reveal_script, LeafVersion::TapScript))
            .expect("Could not create control block")
            .serialize(),
    );

    Transaction {
        version: Version::TWO,
        lock_time: LockTime::ZERO,
        input: vec![TxIn {
            previous_output: OutPoint::null(),
            script_sig: ScriptBuf::new(),
            sequence: Sequence::ENABLE_RBF_NO_LOCKTIME,
            witness,
        }],
        output: vec![TxOut {
            value: Amount::ZERO,
            script_pubkey: sps50_script,
        }],
    }
}
