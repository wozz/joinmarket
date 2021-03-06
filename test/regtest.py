#! /usr/bin/env python
from __future__ import absolute_import
'''Some helper functions for testing'''

import sys
import os
import time
import binascii
import pexpect
import random
import subprocess
import unittest
from commontest import local_command, make_wallets

data_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(data_dir))

import bitcoin as btc

from joinmarket import load_program_config, jm_single
from joinmarket import get_p2pk_vbyte, get_log

python_cmd = 'python2'
yg_cmd = 'yield-generator-basic.py'
#yg_cmd = 'yield-generator-mixdepth.py'
#yg_cmd = 'yield-generator-deluxe.py'

log = get_log()
''' Just some random thoughts to motivate possible tests;
almost none of this has really been done:

Expectations
1. Any bot should run indefinitely irrespective of the input
messages it receives, except bots which perform a finite action

2. A bot must never spend an unacceptably high transaction fee.

3. A bot must explicitly reject interactions with another bot not
respecting the JoinMarket protocol for its version.

4. Bots must never send bitcoin data in the clear over the wire.
'''
'''helper functions put here to avoid polluting the main codebase.'''


class Join2PTests(unittest.TestCase):
    '''This test case intends to simulate
    a single join with a single counterparty. In that sense,
    it's not realistic, because nobody (should) do joins with only 1 maker,
    but this test has the virtue of being the simplest possible thing
    that JoinMarket can do. '''

    def setUp(self):
        #create 2 new random wallets.
        #put 10 coins into the first receive address
        #to allow that bot to start.
        self.wallets = make_wallets(
            2,
            wallet_structures=[[1, 0, 0, 0, 0], [1, 0, 0, 0, 0]],
            mean_amt=10)

    def run_simple_send(self, n, m):
        #start yield generator with wallet1
        yigen_proc = local_command(
            [python_cmd, yg_cmd, str(self.wallets[0]['seed'])],
            bg=True)

        #A significant delay is needed to wait for the yield generator to sync its wallet
        time.sleep(20)

        #run a single sendpayment call with wallet2
        amt = n * 100000000  #in satoshis
        dest_address = btc.privkey_to_address(os.urandom(32), get_p2pk_vbyte())
        try:
            for i in range(m):
                sp_proc = local_command([python_cmd,'sendpayment.py','--yes','-N','1', self.wallets[1]['seed'],\
                                                      str(amt), dest_address])
        except subprocess.CalledProcessError, e:
            if yigen_proc:
                yigen_proc.terminate()
            print e.returncode
            print e.message
            raise

        if yigen_proc:
            yigen_proc.terminate()

        received = jm_single().bc_interface.get_received_by_addr(
            [dest_address], None)['data'][0]['balance']
        if received != amt * m:
            log.debug('received was: ' + str(received) + ' but amount was: ' +
                      str(amt))
            return False
        return True

    def test_simple_send(self):
        self.failUnless(self.run_simple_send(2, 2))


class JoinNPTests(unittest.TestCase):

    def setUp(self):
        self.n = 2
        #create n+1 new random wallets.
        #put 10 coins into the first receive address
        #to allow that bot to start.
        wallet_structures = [[1, 0, 0, 0, 0]] * 3
        self.wallets = make_wallets(3,
                                    wallet_structures=wallet_structures,
                                    mean_amt=10)
        #the sender is wallet (n+1), i.e. index wallets[n]

    def test_n_partySend(self):
        self.failUnless(self.run_nparty_join())

    def run_nparty_join(self):
        yigen_procs = []
        for i in range(self.n):
            ygp = local_command([python_cmd, yg_cmd,\
                                 str(self.wallets[i]['seed'])], bg=True)
            time.sleep(2)  #give it a chance
            yigen_procs.append(ygp)

        #A significant delay is needed to wait for the yield generators to sync
        time.sleep(20)

        #run a single sendpayment call
        amt = 100000000  #in satoshis
        dest_address = btc.privkey_to_address(os.urandom(32), get_p2pk_vbyte())
        try:
            sp_proc = local_command([python_cmd,'sendpayment.py','--yes','-N', str(self.n),\
                                     self.wallets[self.n]['seed'], str(amt), dest_address])
        except subprocess.CalledProcessError, e:
            for ygp in yigen_procs:
                ygp.kill()
            print e.returncode
            print e.message
            raise

        if any(yigen_procs):
            for ygp in yigen_procs:
                ygp.kill()

        received = jm_single().bc_interface.get_received_by_addr(
            [dest_address], None)['data'][0]['balance']
        if received != amt:
            return False
        return True


def main():
    os.chdir(data_dir)
    load_program_config()
    unittest.main()


if __name__ == '__main__':
    main()
