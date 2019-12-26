#!/usr/bin/env python

import argparse
import logging
import yaml

from datetime import timedelta
from golos import Steem
from golos.amount import Amount

log = logging.getLogger('functions')

STEEMIT_INFLATION_RATE_START_PERCENT = 1515
STEEMIT_INFLATION_RATE_STOP_PERCENT = 95
STEEMIT_INFLATION_NARROWING_PERIOD = 250000
STEEMIT_BLOCK_INTERVAL = 3
STEEMIT_BLOCKS_PER_YEAR = 365 * 24 * 60 * 60 / STEEMIT_BLOCK_INTERVAL
STEEMIT_BLOCKS_PER_DAY = 24 * 60 * 60 / STEEMIT_BLOCK_INTERVAL
STEEMIT_100_PERCENT = 10000
STEEMIT_1_PERCENT = STEEMIT_100_PERCENT / 100
STEEMIT_CONTENT_REWARD_PERCENT = 66.67 * STEEMIT_1_PERCENT
STEEMIT_VESTING_FUND_PERCENT = 26.67 * STEEMIT_1_PERCENT
STEEMIT_MAX_WITNESSES = 21
timeshare_weight = 5
top19_weight = 1
witness_pay_normalization_factor = 25


def calc_inflation(
    head_block_num, stop_block_num, virtual_supply, worker_pct, witness_pct, vesting_pct, precise_witness_reward=False
):
    """ Calculate inflation in ranges from start block to stop block
        :param int head_block_num: start block
        :param int stop_block_num: stop block
        :param float virtual_supply: initial virtual_supply
        :param float worker_pct: worker fund inflation percent
        :param float witness_pct: witness pay inflation percent
        :param float vesting_pct: vesting inflation percent
        :param bool precise_witness_reward: calculate precise witness reward; precise but slow;
                                            Gives a little better results (difference is very low)
    """

    worker_reward_per_period = float()
    vesting_reward_per_period = float()
    witness_reward_per_period = float()
    content_reward_per_period = float()

    top19_reward_per_period = float()
    timeshare_reward_per_period = float()

    # increment counter each year
    i = 0

    start_inflation_rate = STEEMIT_INFLATION_RATE_START_PERCENT
    inflation_rate_floor = STEEMIT_INFLATION_RATE_STOP_PERCENT

    while head_block_num < stop_block_num:
        inflation_rate_adjustment = head_block_num / STEEMIT_INFLATION_NARROWING_PERIOD
        current_inflation_rate = max(start_inflation_rate - inflation_rate_adjustment, inflation_rate_floor)
        new_steem = virtual_supply * current_inflation_rate / (STEEMIT_100_PERCENT * STEEMIT_BLOCKS_PER_YEAR)

        if precise_witness_reward:

            worker_reward = new_steem * worker_pct / STEEMIT_100_PERCENT
            witness_reward = new_steem * witness_pct / STEEMIT_100_PERCENT
            vesting_reward = new_steem * vesting_pct / STEEMIT_100_PERCENT
            content_reward = new_steem - worker_reward - witness_reward - vesting_reward

            witness_reward = witness_reward * STEEMIT_MAX_WITNESSES
            if head_block_num % 21 == 0:
                witness_reward = witness_reward * timeshare_weight
                witness_reward = witness_reward / witness_pay_normalization_factor
                # log.debug('per block timeshare reward: {:.3f}'.format(witness_reward))
                timeshare_reward_per_period += witness_reward
            else:
                witness_reward = witness_reward * top19_weight
                witness_reward = witness_reward / witness_pay_normalization_factor
                # log.debug('per block top19 reward: {:.3f}'.format(witness_reward))
                top19_reward_per_period += witness_reward

            new_steem = content_reward + vesting_reward + witness_reward

            worker_reward_per_period += worker_reward
            content_reward_per_period += content_reward
            vesting_reward_per_period += vesting_reward
            witness_reward_per_period += witness_reward

        virtual_supply += new_steem
        # log.debug('per block: {}'.format(new_steem))

        if head_block_num % STEEMIT_BLOCKS_PER_YEAR == 0:
            i += 1
            new_steem_daily = new_steem * STEEMIT_BLOCKS_PER_DAY
            year = head_block_num / STEEMIT_BLOCKS_PER_YEAR
            print(
                'new_steem daily on block {} ({:.0f} years): {:.0f}. Rate: {:.2%}. Virtual Supply: {:,.0f}'.format(
                    head_block_num, year, new_steem_daily, current_inflation_rate / STEEMIT_100_PERCENT, virtual_supply
                )
            )

        head_block_num += 1

    log.debug('last inflation_rate_adjustment: {:.2%}'.format(inflation_rate_adjustment / STEEMIT_100_PERCENT))
    log.debug('last current_inflation_rate: {:.2%}'.format(current_inflation_rate / STEEMIT_100_PERCENT))

    if precise_witness_reward:
        log.info('worker_reward_per_period: {:.0f}'.format(worker_reward_per_period))
        log.info('content_reward_per_period: {:.0f}'.format(content_reward_per_period))
        log.info('vesting_reward_per_period: {:.0f}'.format(vesting_reward_per_period))
        log.info('witness_reward_per_period: {:.0f}'.format(witness_reward_per_period))
        log.debug('timeshare witness reward per period: {:.0f}'.format(timeshare_reward_per_period))
        log.debug('top19 witness reward per period: {:.0f}'.format(top19_reward_per_period))
        sum = content_reward_per_period + vesting_reward_per_period + witness_reward_per_period
        log.info('new_steem_per_period: {:.0f}'.format(sum))

        return sum


def main():

    parser = argparse.ArgumentParser(
        description='calculate inflation rate',
        epilog='Report bugs to: https://github.com/bitfag/golos-witness-tools/issues',
    )
    parser.add_argument('-d', '--debug', action='store_true', help='enable debug output'),
    parser.add_argument('-c', '--config', default='./common.yml', help='specify custom path for config file')
    parser.add_argument('--virtual-supply', type=float, help='override current virtual_supply')
    args = parser.parse_args()

    # create logger
    if args.debug is True:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    log.addHandler(handler)

    # parse config
    with open(args.config, 'r') as ymlfile:
        conf = yaml.safe_load(ymlfile)

    golos = Steem(nodes=conf['node'])

    props = golos.get_dynamic_global_properties()

    head_block_num = props['head_block_number']
    virtual_supply = Amount(props['virtual_supply']).amount
    log.debug('current virtual_supply: {:,.0f}'.format(virtual_supply))

    if args.virtual_supply:
        log.debug('override virtual_supply to: {:,.0f}'.format(args.virtual_supply))
        virtual_supply = args.virtual_supply

    # get inflation params
    median_props = golos.get_chain_properties()
    worker_pct = median_props['worker_reward_percent']
    witness_pct = median_props['witness_reward_percent']
    vesting_pct = median_props['vesting_reward_percent']

    # current daily emission
    days = 1
    delta = timedelta(days=days)
    stop_block_num = head_block_num + delta.total_seconds() / STEEMIT_BLOCK_INTERVAL
    calc_inflation(
        head_block_num,
        stop_block_num,
        virtual_supply,
        worker_pct,
        witness_pct,
        vesting_pct,
        precise_witness_reward=True,
    )

    # long-term emission
    days = 50 * 364
    delta = timedelta(days=days)
    # calculate block_num after X years
    stop_block_num = head_block_num + delta.total_seconds() / STEEMIT_BLOCK_INTERVAL
    calc_inflation(head_block_num, stop_block_num, virtual_supply, worker_pct, witness_pct, vesting_pct)


if __name__ == '__main__':
    main()
