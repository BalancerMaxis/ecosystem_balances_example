from bal_addresses import Ecosystem, BalGauges, Aura, GraphQueries
import csv
import os
import json
from collections import defaultdict
from web3 import Web3
from typing import Dict
from bal_addresses.errors import ChecksumError, NoResultError
from datetime import datetime, timezone



# HOW TO RUN
# Go through the code directly below and understand how/if you want to set any environment variables
# If no environment variables are set a run will generate csvs for all known pools at a block 5 minutes in the past
# Simply run this script with no arguments, outputs can be found in out



# Load config from environment
# Set BLOCK to run on a specific block if unset use timestamp
BLOCK = os.environ.get("BLOCK")
# Set TIMESTAMP to find the next block after a UTC timestamp if BLOCK is missing
TIMESTAMP = os.environ.get("TIMESTAMP")
# Set pool_id to run on only 1 of the pool's listed on the top of this file instead of all of them
POOL_ID = os.environ.get("POOL_ID")
# Multichain SOON:tm:
CHAIN = "mainnet"
# New pools can be added to the run_pools.json to be included in runs
with open("run_pools.json", "r") as f:
    POOLS_TO_RUN_ON = json.load(f)[CHAIN]

# Set block and timestamp based on logic if they are not specified
q = GraphQueries(CHAIN)
if not BLOCK:
    if not TIMESTAMP:
        TIMESTAMP = int(
            datetime.now(timezone.utc).timestamp() - 300)  # Use 5 minutes ago to make sure subgraphs are up to date
    BLOCK = q.get_first_block_after_utc_timestamp(TIMESTAMP)




def get_ecosystem_balances_w_csv(pool_id: str, gauge_address: str, block: int, name: str, chain="mainnet") -> Dict[
    str, int]:
    gauges = BalGauges(chain)
    aura = Aura(chain)
    gauge_address = Web3.toChecksumAddress(gauge_address)
    bpt_balances = defaultdict(float)
    gauge_balances = defaultdict(float)
    aura_balances = defaultdict(float)
    bpts_in_bal_gauge = 0
    bpts_in_aura = 0
    total_circulating_bpts = 0
    total_bpts_counted = 0

    ## Start with raw BPTS
    ecosystem_balances = defaultdict(int, gauges.get_bpt_balances(pool_id, block))
    for address, amount in ecosystem_balances.items():
        ecosystem_balances[address] = float(amount)
        bpt_balances[address] = float(amount)
        total_circulating_bpts += float(amount)

    ## Factor in Gauge Deposits
    # Subtract the gauge itself
    if gauge_address in ecosystem_balances.keys():
        bpts_in_bal_gauge = ecosystem_balances[gauge_address]
        ecosystem_balances[gauge_address] = 0
    else:
        print(
            f"WARNING: there are no BPTs from {pool_id} staked in the gauge at {gauge_address} did you cross wires, or is there no one staked?")

    # Add in Gauge Balances
    checksum = 0
    for address, amount in gauges.get_gauge_deposit_shares(gauge_address, block).items():
        gauge_balances[address] = float(amount)
        ecosystem_balances[address] += float(amount)
        checksum += amount
    if checksum != bpts_in_aura:
        print(
            f"Warning: {bpts_in_bal_gauge} BPTs were found in the deposited in a bal gauge and zeroed out, but {checksum} of 'em where counted as gauge deposits.")

    ## Factor in Aura Deposits
    # Subtract the gauge itself
    aura_staker = aura.AURA_GAUGE_STAKER_BY_CHAIN[chain]
    if aura_staker in ecosystem_balances.keys():
        bpts_in_aura = ecosystem_balances[aura_staker]
        ecosystem_balances[aura_staker] = 0
    else:
        print(
            f"WARNING: there are no BPTs from {pool_id} staked in Aura did you cross wires, or is there no one staked?")

    # Add in Aura Balances
    checksum = 0
    try:
        aura_shares_by_address = aura.get_aura_pool_shares(gauge_address, block).items()
    except NoResultError as e:
        print(e)
        aura_shares_by_address = defaultdict(int)

    for address, amount in aura_shares_by_address:
        aura_balances[address]
        ecosystem_balances[address] += amount
        checksum += amount
    if checksum != bpts_in_aura:
        print(
            f"Warning: {bpts_in_aura} BPTs were found in the aura proxy and zeroed out, but {checksum} of 'em where counted as Aura deposits.")

    ## CHeck everything
    for address, amount in ecosystem_balances.items():
        total_bpts_counted += float(amount)
    print(
        f"Found {total_circulating_bpts} of which {bpts_in_bal_gauge} where staked by an address in a bal gauge and {bpts_in_aura} where deposited on aura at block {block}")
    ## Slight tolerance for rounding
    delta = abs(total_circulating_bpts - total_bpts_counted)
    if delta > 1e-10:
        raise ChecksumError(
            f"initial bpts found {total_circulating_bpts}, final bpts counted:{total_bpts_counted} the delta is {total_circulating_bpts - total_bpts_counted}")

    ## Build CSV
    name = name.replace("/", "-")  # /'s are path structure
    output_file = f"out/{name}/{block}_{pool_id}.csv"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        writer = csv.writer(f)

        writer.writerow(["depositor_address", "bpt_in_wallet", "bpt_in_bal_gauge", "bpt_in_aura", "total_pool_tokens"])
        for depositor, amount in ecosystem_balances.items():
            writer.writerow(
                [depositor, bpt_balances[depositor], gauge_balances[depositor], aura_balances[depositor], amount])
    print("CSV file generated successfully: ", output_file)
    return ecosystem_balances


def main():
    print(f"Using {BLOCK} at unixtime(UTC): {TIMESTAMP}")
    for poolinfo in POOLS_TO_RUN_ON:
        if POOL_ID and poolinfo["pool_id"] != POOL_ID:
            continue
        print(
            f"\n\nRunning on {poolinfo['name']}, pool_id: {poolinfo['pool_id']}, gauge: {poolinfo['gauge']}, block: {BLOCK}\n\n")
        try:
            get_ecosystem_balances_w_csv(
                pool_id=poolinfo["pool_id"],
                gauge_address=poolinfo["gauge"],
                name=poolinfo["name"],
                chain=CHAIN,
                block=BLOCK
            )
        except Exception as e:
            print(f"WARNING: run for {poolinfo['pool_id']} did not finish:\n{e}")


if __name__ == "__main__":
    main()
