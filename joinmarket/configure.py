from __future__ import absolute_import, print_function

import io
import threading

from ConfigParser import SafeConfigParser
from configparser import NoOptionError

import bitcoin as btc
from joinmarket.jsonrpc import JsonRpc
from joinmarket.support import get_log

# config = SafeConfigParser()
# config_location = 'joinmarket.cfg'

log = get_log()


class AttributeDict(object):
    """
    A class to convert a nested Dictionary into an object with key-values
    accessibly using attribute notation (AttributeDict.attribute) instead of
    key notation (Dict["key"]). This class recursively sets Dicts to objects,
    allowing you to recurse down nested dicts (like: AttributeDict.attr.attr)
    """

    def __init__(self, **entries):
        self.add_entries(**entries)

    def add_entries(self, **entries):
        for key, value in entries.items():
            if type(value) is dict:
                self.__dict__[key] = AttributeDict(**value)
            else:
                self.__dict__[key] = value

    def __getitem__(self, key):
        """
        Provides dict-style access to attributes
        """
        return getattr(self, key)


global_singleton = AttributeDict(
        **{'log': log,
           'JM_VERSION': 2,
           'nickname': None,
           'DUST_THRESHOLD': 2730,
           'bc_interface': None,
           'ordername_list': ["absorder", "relorder"],
           'maker_timeout_sec': 30,
           'debug_file_lock': threading.Lock(),
           'debug_file_handle': None,
           'core_alert': None,
           'joinmarket_alert': None,
           'debug_silence': False,
           'config': SafeConfigParser(),
           'config_location': 'joinmarket.cfg'})

# todo: same as above.  decide!!!
# global_singleton = AttributeDict()
# global_singleton.JM_VERSION = 2
# global_singleton.nickname = None
# global_singleton.DUST_THRESHOLD = 2730
# global_singleton.bc_interface = None
# global_singleton.ordername_list = ['absorder', 'relorder']
# global_singleton.maker_timeout_sec = 30
# global_singleton.debug_file_lock = threading.Lock()
# global_singleton.debug_file_handle = None
# global_singleton.core_alert = None
# global_singleton.joinmarket_alert = None
# global_singleton.debug_silence = False
# global_singleton.config = config
# global_singleton.config_location = config_location


def jm_single():
    return global_singleton

# FIXME: Add rpc_* options here in the future!
required_options = {'BLOCKCHAIN': ['blockchain_source', 'network'],
                    'MESSAGING': ['host', 'channel', 'port']}

defaultconfig = \
    """
    [BLOCKCHAIN]
    blockchain_source = blockr
    #options: blockr, bitcoin-rpc, json-rpc, regtest
    # for instructions on bitcoin-rpc read
    # https://github.com/chris-belcher/joinmarket/wiki/Running-JoinMarket-with-Bitcoin-Core-full-node
    network = mainnet
    rpc_host = localhost
    rpc_port = 8332
    rpc_user = bitcoin
    rpc_password = password

    [MESSAGING]
    host = irc.cyberguerrilla.org
    channel = joinmarket-pit
    port = 6697
    usessl = true
    socks5 = false
    socks5_host = localhost
    socks5_port = 9050
    #for tor
    #host = 6dvj6v5imhny3anf.onion
    #port = 6697
    #usessl = true
    #socks5 = true
    maker_timeout_sec = 30

    [POLICY]
    # for dust sweeping, try merge_algorithm = gradual
    # for more rapid dust sweeping, try merge_algorithm = greedy
    # for most rapid dust sweeping, try merge_algorithm = greediest
    # but don't forget to bump your miner fees!
    merge_algorithm = default
    """


def get_config_irc_channel():
    channel = '#' + global_singleton.config.get("MESSAGING", "channel")
    if get_network() == 'testnet':
        channel += '-test'
    return channel


def get_network():
    """Returns network name"""
    return global_singleton.config.get("BLOCKCHAIN", "network")


def get_p2sh_vbyte():
    if get_network() == 'testnet':
        return 0xc4
    else:
        return 0x05


def get_p2pk_vbyte():
    if get_network() == 'testnet':
        return 0x6f
    else:
        return 0x00


def validate_address(addr):
    try:
        ver = btc.get_version_byte(addr)
    except AssertionError:
        return False, 'Checksum wrong. Typo in address?'
    if ver != get_p2pk_vbyte() and ver != get_p2sh_vbyte():
        return False, 'Wrong address version. Testnet/mainnet confused?'
    return True, 'address validated'


def load_program_config():
    loadedFiles = global_singleton.config.read(
            [global_singleton.config_location])
    # Create default config file if not found
    if len(loadedFiles) != 1:
        global_singleton.config.readfp(io.BytesIO(defaultconfig))
        with open(global_singleton.config_location, "w") as configfile:
            configfile.write(defaultconfig)

    # check for sections
    for s in required_options:
        if s not in global_singleton.config.sections():
            raise Exception(
                    "Config file does not contain the required section: " + s)
    # then check for specific options
    for k, v in required_options.iteritems():
        for o in v:
            if o not in global_singleton.config.options(k):
                raise Exception(
                        "Config file does not contain the required option: " + o)

    try:
        global_singleton.maker_timeout_sec = global_singleton.config.getint(
                'MESSAGING', 'maker_timeout_sec')
    except NoOptionError:
        log.debug('maker_timeout_sec not found in .cfg file, '
                  'using default value')

    # configure the interface to the blockchain on startup
    global_singleton.bc_interface = get_blockchain_interface_instance(
            global_singleton.config)


def get_blockchain_interface_instance(_config):
    # todo: refactor joinmarket module to get rid of loops
    # importing here is necessary to avoid import loops
    from joinmarket.blockchaininterface import BitcoinCoreInterface, \
        RegtestBitcoinCoreInterface, BlockrInterface
    from joinmarket.blockchaininterface import CliJsonRpc

    source = _config.get("BLOCKCHAIN", "blockchain_source")
    network = get_network()
    testnet = network == 'testnet'
    if source == 'bitcoin-rpc':
        rpc_host = _config.get("BLOCKCHAIN", "rpc_host")
        rpc_port = _config.get("BLOCKCHAIN", "rpc_port")
        rpc_user = _config.get("BLOCKCHAIN", "rpc_user")
        rpc_password = _config.get("BLOCKCHAIN", "rpc_password")
        rpc = JsonRpc(rpc_host, rpc_port, rpc_user, rpc_password)
        bc_interface = BitcoinCoreInterface(rpc, network)
    elif source == 'json-rpc':
        bitcoin_cli_cmd = _config.get("BLOCKCHAIN", "bitcoin_cli_cmd").split(' ')
        rpc = CliJsonRpc(bitcoin_cli_cmd, testnet)
        bc_interface = BitcoinCoreInterface(rpc, network)
    elif source == 'regtest':
        rpc_host = _config.get("BLOCKCHAIN", "rpc_host")
        rpc_port = _config.get("BLOCKCHAIN", "rpc_port")
        rpc_user = _config.get("BLOCKCHAIN", "rpc_user")
        rpc_password = _config.get("BLOCKCHAIN", "rpc_password")
        rpc = JsonRpc(rpc_host, rpc_port, rpc_user, rpc_password)
        bc_interface = RegtestBitcoinCoreInterface(rpc)
    elif source == 'blockr':
        bc_interface = BlockrInterface(testnet)
    else:
        raise ValueError("Invalid blockchain source")
    return bc_interface
