# (c) Copyright 2020 by Coinkite Inc. This file is covered by license found in COPYING-CC.
#
# Exporting of wallet files and similar things.
#
import pytest, time, struct, os
from pycoin.key.BIP32Node import BIP32Node
from base64 import b64encode
from binascii import b2a_hex, a2b_hex
from ckcc_protocol.protocol import CCProtocolPacker, CCProtoError, CCUserRefused
from ckcc_protocol.constants import *
from helpers import xfp2str
import json
from conftest import simulator_fixed_xfp, simulator_fixed_xprv
from ckcc_protocol.constants import AF_CLASSIC, AF_P2WPKH, AF_P2WSH_P2SH

@pytest.mark.parametrize('acct_num', [ None, '0', '99', '123'])
def test_export_core(dev, acct_num, cap_menu, pick_menu_item, goto_home, cap_story, need_keypress, microsd_path, bitcoind_wallet):
    # test UX and operation of the 'bitcoin core' wallet export
    from pycoin.contrib.segwit_addr import encode as sw_encode

    goto_home()
    pick_menu_item('Advanced')
    pick_menu_item('MicroSD Card')
    pick_menu_item('Export Wallet')
    pick_menu_item('Bitcoin Core')

    time.sleep(0.1)
    title, story = cap_story()

    assert 'This saves' in story
    assert 'run that command' in story

    assert 'Press 1 to' in story
    if acct_num is not None:
        need_keypress('1')
        time.sleep(0.1)
        for n in acct_num:
            need_keypress(n)
    else:
        acct_num = '0'

    need_keypress('y')

    time.sleep(0.1)
    title, story = cap_story()

    assert 'Bitcoin Core file written' in story
    fname = story.split('\n')[-1]

    need_keypress('y')

    path = microsd_path(fname)
    addrs = []
    js = None
    with open(path, 'rt') as fp:
        for ln in fp:
            if 'importmulti' in ln:
                assert ln.startswith("importmulti '")
                assert ln.endswith("'\n")
                assert not js, "dup importmulti lines"
                js = ln[13:-2]
            elif '=>' in ln:
                path, addr = ln.strip().split(' => ', 1)
                assert path.startswith(f"m/84'/1'/{acct_num}'/0")
                assert addr.startswith('tb1q')
                sk = BIP32Node.from_wallet_key(simulator_fixed_xprv).subkey_for_path(path[2:])
                h20 = sk.hash160()
                assert addr == sw_encode(addr[0:2], 0, h20)
                addrs.append(addr)

    assert len(addrs) == 3

    obj = json.loads(js)
    xfp = xfp2str(simulator_fixed_xfp).lower()

    for n, here in enumerate(obj):
        assert here['range'] == [0, 1000]
        assert here['timestamp'] == 'now'
        assert here['internal'] == bool(n)
        assert here['keypool'] == True
        assert here['watchonly'] == True

        d = here['desc']
        desc, chk = d.split('#', 1)
        assert len(chk) == 8
        assert desc.startswith(f'wpkh([{xfp}/84h/1h/{acct_num}h]')

        expect = BIP32Node.from_wallet_key(simulator_fixed_xprv)\
                    .subkey_for_path(f"84'/1'/{acct_num}'.pub").hwif()

        assert expect in desc
        assert expect+f'/{n}/*' in desc

    # test against bitcoind
    for x in obj:
        x['label'] = 'testcase'
    bitcoind_wallet.importmulti(obj)
    x = bitcoind_wallet.getaddressinfo(addrs[-1])
    from pprint import pprint
    pprint(x)
    assert x['address'] == addrs[-1]
    assert x['label'] == 'testcase'
    assert x['iswatchonly'] == True
    assert x['iswitness'] == True
    assert x['hdkeypath'] == f"m/84'/1'/{acct_num}'/0/%d" % (len(addrs)-1)

def test_export_wasabi(dev, cap_menu, pick_menu_item, goto_home, cap_story, need_keypress, microsd_path):
    # test UX and operation of the 'wasabi wallet export'

    goto_home()
    pick_menu_item('Advanced')
    pick_menu_item('MicroSD Card')
    pick_menu_item('Export Wallet')
    pick_menu_item('Wasabi Wallet')

    time.sleep(0.1)
    title, story = cap_story()

    assert 'This saves a skeleton Wasabi' in story

    need_keypress('y')

    time.sleep(0.1)
    title, story = cap_story()

    assert 'wallet file written' in story
    fname = story.split('\n')[-1]

    need_keypress('y')

    path = microsd_path(fname)
    with open(path, 'rt') as fp:
        obj = json.load(fp)

        assert 'MasterFingerprint' in obj
        assert 'ExtPubKey' in obj
        assert 'ColdCardFirmwareVersion' in obj
        
        xpub = obj['ExtPubKey']
        assert xpub.startswith('xpub')      # even for testnet

        assert obj['MasterFingerprint'] == xfp2str(simulator_fixed_xfp)

        got = BIP32Node.from_wallet_key(xpub)
        expect = BIP32Node.from_wallet_key(simulator_fixed_xprv).subkey_for_path("84'/0'/0'.pub")

        assert got.sec() == expect.sec()

    os.unlink(path)

        
@pytest.mark.parametrize('mode', [ "Legacy (P2PKH)", "P2SH-Segwit", "Native Segwit"])
@pytest.mark.parametrize('acct_num', [ None, '0', '99', '123'])
def test_export_electrum(mode, acct_num, dev, cap_menu, pick_menu_item, goto_home, cap_story, need_keypress, microsd_path):
    # lightly test electrum wallet export

    goto_home()
    pick_menu_item('Advanced')
    pick_menu_item('MicroSD Card')
    pick_menu_item('Export Wallet')
    pick_menu_item('Electrum Wallet')

    time.sleep(0.1)
    title, story = cap_story()

    assert 'This saves a skeleton Electrum wallet' in story

    assert 'Press 1 to' in story
    if acct_num is not None:
        need_keypress('1')
        time.sleep(0.1)
        for n in acct_num:
            need_keypress(n)

    need_keypress('y')

    time.sleep(0.1)
    pick_menu_item(mode)

    time.sleep(0.1)
    title, story = cap_story()

    assert 'wallet file written' in story
    fname = story.split('\n')[-1]

    need_keypress('y')

    path = microsd_path(fname)
    with open(path, 'rt') as fp:
        obj = json.load(fp)

        ks = obj['keystore']
        assert ks['ckcc_xfp'] == simulator_fixed_xfp

        assert ks['hw_type'] == 'coldcard'
        assert ks['type'] == 'hardware'

        deriv = ks['derivation']
        assert deriv.startswith('m/')
        assert int(deriv.split("/")[1][:-1]) in {44, 84, 49}        # weak
        assert deriv.split("/")[3] == (acct_num or '0')+"'"

        xpub = ks['xpub']
        assert xpub[1:4] == 'pub'

        if xpub[0] in 'tx': 
            # no slip132 here

            got = BIP32Node.from_wallet_key(xpub)
            expect = BIP32Node.from_wallet_key(simulator_fixed_xprv).subkey_for_path(deriv[2:])

            assert got.sec() == expect.sec()

    os.unlink(path)

@pytest.mark.parametrize('acct_num', [ None, '99', '123'])
def test_export_coldcard(acct_num, dev, cap_menu, pick_menu_item, goto_home, cap_story, need_keypress, microsd_path, addr_vs_path):
    from pycoin.contrib.segwit_addr import encode as sw_encode

    # test UX and values produced.
    goto_home()
    pick_menu_item('Advanced')
    pick_menu_item('MicroSD Card')
    pick_menu_item('Export Wallet')
    pick_menu_item('Generic JSON')

    time.sleep(0.1)
    title, story = cap_story()
    assert 'Saves JSON file' in story

    need_keypress('y')
    if acct_num:
        for n in acct_num:
            need_keypress(n)
    else:
        acct_num = '0'
    need_keypress('y')

    time.sleep(0.1)
    title, story = cap_story()

    assert 'Generic Export file written' in story
    fname = story.split('\n')[-1]

    need_keypress('y')

    path = microsd_path(fname)
    with open(path, 'rt') as fp:
        obj = json.load(fp)

        for fn in ['xfp', 'xpub', 'chain']:
            assert fn in obj
            assert obj[fn]
        assert obj['account'] == int(acct_num or 0)

        for fn in ['bip44', 'bip49', 'bip84', 'bip48_1', 'bip48_2']:
            assert fn in obj
            v = obj[fn]
            assert all([i in v for i in ['deriv', 'name', 'first', 'xpub', 'xfp']])

            if 'bip48' not in fn:
                assert v['deriv'].endswith(f"'/{acct_num}'")
            else:
                b48n = fn[-1]
                assert v['deriv'].endswith(f"'/{acct_num}'/{b48n}'")

            node = BIP32Node.from_wallet_key(v['xpub'])
            first = node.subkey_for_path('0/0')
            addr = v['first']

            if fn == 'bip44':
                assert first.address() == v['first']
                addr_vs_path(addr, v['deriv'] + '/0/0', AF_CLASSIC)
            elif 'bip48' in fn:
                assert addr == None
            else:
                assert v['_pub'][1:4] == 'pub'

                if fn == 'bip84':
                    h20 = first.hash160()
                    assert addr == sw_encode(addr[0:2], 0, h20)
                    addr_vs_path(addr, v['deriv'] + '/0/0', AF_P2WPKH)
                else:
                    addr_fmt = AF_P2WSH_P2SH
                    # don't have test logic for verifying these addrs

# EOF
