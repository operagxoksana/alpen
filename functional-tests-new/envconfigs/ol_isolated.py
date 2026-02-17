"""
OL Isolated environment configuration.

This environment starts the OL (Orchestration Layer) without the EE (Execution Engine),
allowing tests to verify OL behavior in isolation. Genesis accounts can be configured
with predefined balances and states for testing withdrawal and other account operations.
"""

from typing import cast

import flexitest

from common.config import BitcoindConfig, ServiceType
from common.config.params import GenesisAccountData, GenesisL1View, OLParams
from factories.bitcoin import BitcoinFactory
from factories.strata import StrataFactory


def make_test_account_id(ref_byte: int = 0x42) -> str:
    """
    Create a test account ID hex string.

    Args:
        ref_byte: The identifying byte for the account (default 0x42).

    Returns:
        64-character hex string (32 bytes).
    """
    # Account ID is 32 bytes with the last byte being the ref_byte
    return "00" * 31 + f"{ref_byte:02x}"


class OLIsolatedEnvConfig(flexitest.EnvConfig):
    """
    OL Isolated environment: Starts Bitcoin and OL without EE.

    This configuration:
    - Starts a Bitcoin regtest node
    - Starts a Strata sequencer with custom genesis accounts
    - Does NOT start an EE (reth) node

    Genesis accounts can be configured with:
    - AlwaysAccept predicate (no proof verification)
    - Custom initial balance
    - Custom inner state
    """

    def __init__(
        self,
        pre_generate_blocks: int = 110,
        genesis_accounts: dict[str, GenesisAccountData] | None = None,
    ):
        """
        Initialize the OL isolated environment.

        Args:
            pre_generate_blocks: Number of Bitcoin blocks to generate at startup.
            genesis_accounts: Dict of account_id_hex -> GenesisAccountData for
                             accounts to create at genesis. If None, a default
                             test account with 1.5 BTC is created.
        """
        self.pre_generate_blocks = pre_generate_blocks

        if genesis_accounts is None:
            # Default: create a test snark account with 20 BTC (2B sats)
            test_account_id = make_test_account_id(0x42)
            self.genesis_accounts = {
                test_account_id: GenesisAccountData(
                    predicate="AlwaysAccept",
                    inner_state="00" * 32,  # Zero state root
                    balance=2_000_000_000,  # 20 BTC in satoshis
                )
            }
        else:
            self.genesis_accounts = genesis_accounts

    def init(self, ectx: flexitest.EnvContext) -> flexitest.LiveEnv:
        btc_factory = cast(BitcoinFactory, ectx.get_factory(ServiceType.Bitcoin))
        strata_factory = cast(StrataFactory, ectx.get_factory(ServiceType.Strata))

        # Start Bitcoin
        bitcoind = btc_factory.create_regtest()
        bitcoind.wait_for_ready(timeout=10)

        # Create wallet and generate initial blocks
        btc_rpc = bitcoind.create_rpc()
        btc_rpc.proxy.createwallet("testwallet")

        if self.pre_generate_blocks > 0:
            addr = btc_rpc.proxy.getnewaddress()
            btc_rpc.proxy.generatetoaddress(self.pre_generate_blocks, addr)

        # Create Bitcoin config
        bitcoind_config = BitcoindConfig(
            rpc_url=f"http://localhost:{bitcoind.get_prop('rpc_port')}",
            rpc_user=bitcoind.get_prop("rpc_user"),
            rpc_password=bitcoind.get_prop("rpc_password"),
        )

        # Get genesis L1 view
        genesis_l1 = GenesisL1View.at_latest_block(btc_rpc)

        # Create Strata sequencer with custom OL params
        # We pass the genesis accounts via config_overrides or factory modification
        strata = strata_factory.create_node(
            bitcoind_config,
            genesis_l1,
            is_sequencer=True,
            ol_params=OLParams(accounts=self.genesis_accounts).with_genesis_l1(
                genesis_l1
            ),
        )
        strata.wait_for_ready(timeout=30)

        services = {
            ServiceType.Bitcoin: bitcoind,
            ServiceType.Strata: strata,
        }

        return flexitest.LiveEnv(services)


# Convenience instances for common configurations
OL_ISOLATED_DEFAULT = OLIsolatedEnvConfig()
