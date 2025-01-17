import base64
import random
import time

import parse
from behave import given, register_type, then, when
from nacl.signing import SigningKey

from algosdk import (
    account,
    auction,
    encoding,
    kmd,
    logic,
    mnemonic,
    util,
    wallet,
    transaction,
)


@parse.with_pattern(r".*")
def parse_string(text):
    return text


register_type(MaybeString=parse_string)


token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
indexer_port = 59999
algod_port = 60000
kmd_port = 60001

DEV_ACCOUNT_INITIAL_MICROALGOS: int = 10_000_000


def wait_for_algod_transaction_processing_to_complete():
    """
    wait_for_algod_transaction_processing_to_complete is a Dev mode helper method that's a rough analog to `context.app_acl.status_after_block(last_round + 2)`.
     * <p>
     * Since Dev mode produces blocks on a per transaction basis, it's possible algod generates a block _before_ the corresponding SDK call to wait for a block.
     * Without _any_ wait, it's possible the SDK looks for the transaction before algod completes processing.
     * So, the method performs a local sleep to simulate waiting for a block.
    """
    time.sleep(0.5)


# Initialize a transient account in dev mode to make payment transactions.
def initialize_account(context, account):
    payment = transaction.PaymentTxn(
        sender=context.accounts[0],
        sp=context.app_acl.suggested_params(),
        receiver=account,
        amt=DEV_ACCOUNT_INITIAL_MICROALGOS,
    )
    signed_payment = context.wallet.sign_transaction(payment)
    context.app_acl.send_transaction(signed_payment)
    # Wait to let transaction get confirmed in dev mode in v1.
    wait_for_algod_transaction_processing_to_complete()


# Send a self-payment transaction to itself to advance blocks in dev mode.
def self_pay_transactions(context, num_txns=1):
    if not hasattr(context, "dev_pk"):
        context.dev_sk, context.dev_pk = account.generate_account()
        initialize_account(context, context.dev_pk)
    for _ in range(num_txns):
        payment = transaction.PaymentTxn(
            sender=context.dev_pk,
            sp=context.app_acl.suggested_params(),
            receiver=context.dev_pk,
            amt=random.randint(1, int(DEV_ACCOUNT_INITIAL_MICROALGOS * 0.01)),
        )
        signed_payment = payment.sign(context.dev_sk)
        context.app_acl.send_transaction(signed_payment)
        # Wait to let transaction get confirmed in dev mode in v1.
        wait_for_algod_transaction_processing_to_complete()


@when("I create a wallet")
def create_wallet(context):
    context.wallet_name = "Walletpy"
    context.wallet_pswd = ""
    context.wallet_id = context.kcl.create_wallet(
        context.wallet_name, context.wallet_pswd
    )["id"]


@then("the wallet should exist")
def wallet_exist(context):
    wallets = context.kcl.list_wallets()
    wallet_names = [w["name"] for w in wallets]
    assert context.wallet_name in wallet_names


@when("I get the wallet handle")
def get_handle(context):
    context.handle = context.kcl.init_wallet_handle(
        context.wallet_id, context.wallet_pswd
    )


@then("I can get the master derivation key")
def get_mdk(context):
    mdk = context.kcl.export_master_derivation_key(
        context.handle, context.wallet_pswd
    )
    assert mdk


@when("I rename the wallet")
def rename_wallet(context):
    context.wallet_name = "Walletpy_new"
    context.kcl.rename_wallet(
        context.wallet_id, context.wallet_pswd, context.wallet_name
    )


@then("I can still get the wallet information with the same handle")
def get_wallet_info(context):
    info = context.kcl.get_wallet(context.handle)
    assert info


@when("I renew the wallet handle")
def renew_handle(context):
    if not hasattr(context, "handle"):
        context.handle = context.kcl.init_wallet_handle(
            context.wallet_id, context.wallet_pswd
        )
    context.kcl.renew_wallet_handle(context.handle)


@when("I release the wallet handle")
def release_handle(context):
    context.kcl.release_wallet_handle(context.handle)


@then("the wallet handle should not work")
def try_handle(context):
    try:
        context.renew_wallet_handle(context.handle)
        context.error = False
    except:
        context.error = True
    assert context.error


@given(
    'payment transaction parameters {fee} {fv} {lv} "{gh}" "{to}" "{close}" {amt} "{gen}" "{note}"'
)
def txn_params(context, fee, fv, lv, gh, to, close, amt, gen, note):
    context.fee = int(fee)
    context.fv = int(fv)
    context.lv = int(lv)
    context.gh = gh
    context.to = to
    context.amt = int(amt)
    if context.fee == 0:
        context.params = transaction.SuggestedParams(
            context.fee, context.fv, context.lv, context.gh, gen, flat_fee=True
        )
    else:
        context.params = transaction.SuggestedParams(
            context.fee, context.fv, context.lv, context.gh, gen
        )
    if close == "none":
        context.close = None
    else:
        context.close = close
    if note == "none":
        context.note = None
    else:
        context.note = base64.b64decode(note)
    if gen == "none":
        context.gen = None
    else:
        context.gen = gen


@given('mnemonic for private key "{mn}"')
def mn_for_sk(context, mn):
    context.mn = mn
    context.sk = mnemonic.to_private_key(mn)
    context.pk = account.address_from_private_key(context.sk)


@given('multisig addresses "{addresses}"')
def msig_addresses(context, addresses):
    addresses = addresses.split(" ")
    context.msig = transaction.Multisig(1, 2, addresses)


@when("I create the multisig payment transaction")
def create_msigpaytxn(context):
    context.txn = transaction.PaymentTxn(
        context.msig.address(),
        context.params,
        context.to,
        context.amt,
        context.close,
        context.note,
    )
    context.mtx = transaction.MultisigTransaction(context.txn, context.msig)


@when("I create the multisig payment transaction with zero fee")
def create_msigpaytxn_zero_fee(context):
    context.txn = transaction.PaymentTxn(
        context.msig.address(),
        context.params,
        context.to,
        context.amt,
        context.close,
        context.note,
    )
    context.mtx = transaction.MultisigTransaction(context.txn, context.msig)


@when("I sign the multisig transaction with the private key")
def sign_msig(context):
    context.mtx.sign(context.sk)


@when("I sign the transaction with the private key")
def sign_with_sk(context):
    context.stx = context.txn.sign(context.sk)


@then('the signed transaction should equal the golden "{golden}"')
def equal_golden(context, golden):
    assert encoding.msgpack_encode(context.stx) == golden


@then('the multisig address should equal the golden "{golden}"')
def equal_msigaddr_golden(context, golden):
    assert context.msig.address() == golden


@then('the multisig transaction should equal the golden "{golden}"')
def equal_msig_golden(context, golden):
    if not encoding.msgpack_encode(context.mtx) == golden:
        print(encoding.msgpack_encode(context.mtx))
        print(golden)
    assert encoding.msgpack_encode(context.mtx) == golden


@when("I get versions with algod")
def acl_v(context):
    context.versions = context.app_acl.versions()["versions"]


@then("v1 should be in the versions")
def v1_in_versions(context):
    assert "v1" in context.versions


@then("v2 should be in the versions")
def v2_in_versions(context):
    assert "v2" in context.versions


@when("I get versions with kmd")
def kcl_v(context):
    context.versions = context.kcl.versions()


@when("I import the multisig")
def import_msig(context):
    context.wallet.import_multisig(context.msig)


@then("the multisig should be in the wallet")
def msig_in_wallet(context):
    msigs = context.wallet.list_multisig()
    assert context.msig.address() in msigs


@when("I export the multisig")
def exp_msig(context):
    context.exp = context.wallet.export_multisig(context.msig.address())


@then("the multisig should equal the exported multisig")
def msig_eq(context):
    assert encoding.msgpack_encode(context.msig) == encoding.msgpack_encode(
        context.exp
    )


@when("I delete the multisig")
def delete_msig(context):
    context.wallet.delete_multisig(context.msig.address())


@then("the multisig should not be in the wallet")
def msig_not_in_wallet(context):
    msigs = context.wallet.list_multisig()
    assert context.msig.address() not in msigs


@when("I generate a key using kmd")
def gen_key_kmd(context):
    context.pk = context.wallet.generate_key()


@when("I generate a key using kmd for rekeying and fund it")
def gen_rekey_kmd(context):
    context.rekey = context.wallet.generate_key()
    initialize_account(context, context.rekey)


@then("the key should be in the wallet")
def key_in_wallet(context):
    keys = context.wallet.list_keys()
    assert context.pk in keys


@when("I delete the key")
def delete_key(context):
    context.wallet.delete_key(context.pk)


@then("the key should not be in the wallet")
def key_not_in_wallet(context):
    keys = context.wallet.list_keys()
    assert context.pk not in keys


@when("I generate a key")
def gen_key(context):
    context.sk, context.pk = account.generate_account()
    context.old = context.pk


@when("I import the key")
def import_key(context):
    context.wallet.import_key(context.sk)


@then("the private key should be equal to the exported private key")
def sk_eq_export(context):
    exp = context.wallet.export_key(context.pk)
    assert context.sk == exp
    context.wallet.delete_key(context.pk)


@given("a kmd client")
def kmd_client(context):
    kmd_address = "http://localhost:" + str(kmd_port)
    context.kcl = kmd.KMDClient(token, kmd_address)


@given("wallet information")
def wallet_info(context):
    context.wallet_name = "unencrypted-default-wallet"
    context.wallet_pswd = ""
    context.wallet = wallet.Wallet(
        context.wallet_name, context.wallet_pswd, context.kcl
    )
    context.wallet_id = context.wallet.id
    context.accounts = context.wallet.list_keys()


def default_txn_with_addr(context, amt, note, sender_addr):
    params = context.app_acl.suggested_params()
    context.last_round = params.first
    if note == "none":
        note = None
    else:
        note = base64.b64decode(note)
    context.txn = transaction.PaymentTxn(
        sender_addr, params, context.accounts[1], int(amt), note=note
    )
    context.pk = sender_addr


@given('default transaction with parameters {amt} "{note}"')
def default_txn(context, amt, note):
    default_txn_with_addr(context, amt, note, context.accounts[0])


@given('default transaction with parameters {amt} "{note}" and rekeying key')
def default_txn_rekey(context, amt, note):
    default_txn_with_addr(context, amt, note, context.rekey)


@given('default multisig transaction with parameters {amt} "{note}"')
def default_msig_txn(context, amt, note):
    params = context.app_acl.suggested_params()
    context.last_round = params.first
    if note == "none":
        note = None
    else:
        note = base64.b64decode(note)
    context.msig = transaction.Multisig(1, 1, context.accounts)
    context.txn = transaction.PaymentTxn(
        context.msig.address(),
        params,
        context.accounts[1],
        int(amt),
        note=note,
    )
    context.mtx = transaction.MultisigTransaction(context.txn, context.msig)
    context.pk = context.accounts[0]


@when("I get the private key")
def get_sk(context):
    context.sk = context.wallet.export_key(context.pk)


@when("I send the transaction")
def send_txn(context):
    try:
        context.app_txid = context.app_acl.send_transaction(context.stx)
    except:
        context.error = True


@when("I send the kmd-signed transaction")
def send_txn_kmd(context):
    context.app_txid = context.app_acl.send_transaction(context.stx_kmd)


@when("I send the bogus kmd-signed transaction")
def send_txn_kmd_bogus(context):
    try:
        context.app_acl.send_transaction(context.stx_kmd)
    except:
        context.error = True


@when("I send the multisig transaction")
def send_msig_txn(context):
    try:
        context.app_acl.send_transaction(context.mtx)
    except:
        context.error = True


@then("the transaction should not go through")
def txn_fail(context):
    assert context.error


@when("I sign the transaction with kmd")
def sign_kmd(context):
    context.stx_kmd = context.wallet.sign_transaction(context.txn)


@then("the signed transaction should equal the kmd signed transaction")
def sign_both_equal(context):
    assert encoding.msgpack_encode(context.stx) == encoding.msgpack_encode(
        context.stx_kmd
    )


@when("I sign the multisig transaction with kmd")
def sign_msig_kmd(context):
    context.mtx_kmd = context.wallet.sign_multisig_transaction(
        context.accounts[0], context.mtx
    )


@then(
    "the multisig transaction should equal the kmd signed multisig transaction"
)
def sign_msig_both_equal(context):
    assert encoding.msgpack_encode(context.mtx) == encoding.msgpack_encode(
        context.mtx_kmd
    )


@then("I get the ledger supply")
def get_ledger(context):
    context.app_acl.ledger_supply()


@then("the node should be healthy")
def check_health(context):
    assert context.app_acl.health() == None


@when("I create a bid")
def create_bid(context):
    context.sk, pk = account.generate_account()
    context.bid = auction.Bid(pk, 1, 2, 3, pk, 4)


@when("I encode and decode the bid")
def enc_dec_bid(context):
    context.bid = encoding.msgpack_decode(encoding.msgpack_encode(context.bid))


@then("the bid should still be the same")
def check_bid(context):
    assert context.sbid == context.old


@when("I sign the bid")
def sign_bid(context):
    context.sbid = context.bid.sign(context.sk)
    context.old = context.bid.sign(context.sk)


@when("I decode the address")
def decode_addr(context):
    context.pk = encoding.decode_address(context.pk)


@when("I encode the address")
def encode_addr(context):
    context.pk = encoding.encode_address(context.pk)


@then("the address should still be the same")
def check_addr(context):
    assert context.pk == context.old


@when("I convert the private key back to a mnemonic")
def sk_to_mn(context):
    context.mn = mnemonic.from_private_key(context.sk)


@then('the mnemonic should still be the same as "{mn}"')
def check_mn(context, mn):
    assert context.mn == mn


@given('mnemonic for master derivation key "{mn}"')
def mn_for_mdk(context, mn):
    context.mn = mn
    context.mdk = mnemonic.to_master_derivation_key(mn)


@when("I convert the master derivation key back to a mnemonic")
def mdk_to_mn(context):
    context.mn = mnemonic.from_master_derivation_key(context.mdk)


@when("I create the flat fee payment transaction")
def create_paytxn_flat_fee(context):
    context.params.flat_fee = True
    context.txn = transaction.PaymentTxn(
        context.pk,
        context.params,
        context.to,
        context.amt,
        context.close,
        context.note,
    )


@given('encoded multisig transaction "{mtx}"')
def dec_mtx(context, mtx):
    context.mtx = encoding.msgpack_decode(mtx)


@when("I append a signature to the multisig transaction")
def append_mtx(context):
    context.mtx.sign(context.sk)


@given('encoded multisig transactions "{msigtxns}"')
def mtxs(context, msigtxns):
    context.mtxs = msigtxns.split(" ")
    context.mtxs = [encoding.msgpack_decode(m) for m in context.mtxs]


@when("I merge the multisig transactions")
def merge_mtxs(context):
    context.mtx = transaction.MultisigTransaction.merge(context.mtxs)


@when("I convert {microalgos} microalgos to algos and back")
def convert_algos(context, microalgos):
    context.microalgos = util.algos_to_microalgos(
        util.microalgos_to_algos(int(microalgos))
    )


@then("it should still be the same amount of microalgos {microalgos}")
def check_microalgos(context, microalgos):
    assert int(microalgos) == context.microalgos


@then("I can get account information")
def new_acc_info(context):
    context.app_acl.account_info(context.pk)
    context.wallet.delete_key(context.pk)


@given("default V2 key registration transaction {type}")
def default_v2_keyreg_txn(context, type):
    context.params = context.app_acl.suggested_params()
    context.pk = context.accounts[0]
    context.txn = buildTxn(type, context.pk, context.params)


@given("default asset creation transaction with total issuance {total}")
def default_asset_creation_txn(context, total):
    context.total = int(total)
    params = context.app_acl.suggested_params()
    context.last_round = params.first
    context.pk = context.accounts[0]
    asset_name = "asset"
    unit_name = "unit"
    params.fee = 1
    context.txn = transaction.AssetConfigTxn(
        context.pk,
        params,
        total=context.total,
        default_frozen=False,
        unit_name=unit_name,
        asset_name=asset_name,
        manager=context.pk,
        reserve=context.pk,
        freeze=context.pk,
        clawback=context.pk,
    )

    context.expected_asset_info = {
        "default-frozen": False,
        "unit-name": "unit",
        "name": "asset",
        "manager": context.pk,
        "reserve": context.pk,
        "freeze": context.pk,
        "clawback": context.pk,
        "creator": context.pk,
        "total": context.total,
        "decimals": 0,
        "metadata-hash": None,
        "url": "",
    }


@given("default-frozen asset creation transaction with total issuance {total}")
def default_frozen_asset_creation_txn(context, total):
    context.total = int(total)
    params = context.app_acl.suggested_params()
    context.last_round = params.first
    context.pk = context.accounts[0]
    asset_name = "asset"
    unit_name = "unit"
    params.fee = 1
    context.txn = transaction.AssetConfigTxn(
        context.pk,
        params,
        total=context.total,
        default_frozen=True,
        unit_name=unit_name,
        asset_name=asset_name,
        manager=context.pk,
        reserve=context.pk,
        freeze=context.pk,
        clawback=context.pk,
    )

    context.expected_asset_info = {
        "default-frozen": False,
        "unit-name": "unit",
        "name": "asset",
        "manager": context.pk,
        "reserve": context.pk,
        "freeze": context.pk,
        "clawback": context.pk,
        "creator": context.pk,
        "total": context.total,
        "decimals": 0,
        "metadata-hash": None,
        "url": "",
    }


@given("asset test fixture")
def asset_fixture(context):
    context.expected_asset_info = dict()
    context.rcv = context.accounts[1]


@when("I update the asset index")
def update_asset_index(context):
    assets = context.app_acl.account_info(context.pk)["created-assets"]
    indices = [a["index"] for a in assets]
    context.asset_index = max(indices)


@when("I get the asset info")
def get_asset_info(context):
    context.asset_info = context.app_acl.asset_info(context.asset_index)


@then("the asset info should match the expected asset info")
def asset_info_match(context):
    for k in context.expected_asset_info:
        assert (
            context.expected_asset_info[k]
            == context.asset_info["params"].get(k)
        ) or (
            (not context.expected_asset_info[k])
            and (not context.asset_info["params"].get(k))
        )


@when("I create an asset destroy transaction")
def create_asset_destroy_txn(context):
    context.txn = transaction.AssetConfigTxn(
        context.pk,
        context.app_acl.suggested_params(),
        index=context.asset_index,
        strict_empty_address_check=False,
    )


@then("I should be unable to get the asset info")
def err_asset_info(context):
    err = False
    try:
        context.app_acl.asset_info(context.asset_index)
    except:
        err = True
    assert err


@when("I create a no-managers asset reconfigure transaction")
def no_manager_txn(context):
    context.txn = transaction.AssetConfigTxn(
        context.pk,
        context.app_acl.suggested_params(),
        index=context.asset_index,
        reserve=context.pk,
        clawback=context.pk,
        freeze=context.pk,
        strict_empty_address_check=False,
    )

    context.expected_asset_info["manager"] = ""


@when(
    "I create a transaction for a second account, signalling asset acceptance"
)
def accept_asset_txn(context):
    params = context.app_acl.suggested_params()
    context.txn = transaction.AssetTransferTxn(
        context.rcv, params, context.rcv, 0, context.asset_index
    )


@when(
    "I create a transaction transferring {amount} assets from creator to a second account"
)
def transfer_assets(context, amount):
    params = context.app_acl.suggested_params()
    context.txn = transaction.AssetTransferTxn(
        context.pk, params, context.rcv, int(amount), context.asset_index
    )


@when(
    "I create a transaction transferring {amount} assets from a second account to creator"
)
def transfer_assets_to_creator(context, amount):
    params = context.app_acl.suggested_params()
    context.txn = transaction.AssetTransferTxn(
        context.rcv, params, context.pk, int(amount), context.asset_index
    )


@then("the creator should have {exp_balance} assets remaining")
def check_asset_balance(context, exp_balance):
    asset_info_resp = context.app_acl.account_info(context.pk)["assets"]
    for a in asset_info_resp:
        if a["asset-id"] == context.asset_index:
            assert a["amount"] == int(exp_balance)


@when("I create a freeze transaction targeting the second account")
def freeze_txn(context):
    params = context.app_acl.suggested_params()
    context.txn = transaction.AssetFreezeTxn(
        context.pk, params, context.asset_index, context.rcv, True
    )


@when("I create an un-freeze transaction targeting the second account")
def unfreeze_txn(context):
    params = context.app_acl.suggested_params()
    context.txn = transaction.AssetFreezeTxn(
        context.pk, params, context.asset_index, context.rcv, False
    )


@when(
    "I create a transaction revoking {amount} assets from a second account to creator"
)
def revoke_txn(context, amount):
    params = context.app_acl.suggested_params()
    context.txn = transaction.AssetTransferTxn(
        context.pk,
        params,
        context.pk,
        int(amount),
        context.asset_index,
        revocation_target=context.rcv,
    )


@given("I sign the transaction with the private key")
def given_sign_with_sk(context):
    # python cucumber considers "Given foo" and "When foo" to be distinct,
    # but we don't want them to be. So, call the other function
    sign_with_sk(context)


@given("I send the transaction")
def given_send_txn(context):
    # python cucumber considers "Given foo" and "When foo" to be distinct,
    # but we don't want them to be. So, call the other function
    send_txn(context)


@when('mnemonic for private key "{mn}"')
def when_mn_for_sk(context, mn):
    # python cucumber considers "Given foo" and "When foo" to be distinct,
    # but we don't want them to be. So, call the other function
    mn_for_sk(context, mn)


@when('I set the from address to "{from_addr}"')
def set_from_to(context, from_addr):
    context.txn.sender = from_addr


@when("I add a rekeyTo field with the private key algorand address")
def add_rekey_to_sk(context):
    context.txn.rekey_to = account.address_from_private_key(context.sk)


@when('I add a rekeyTo field with address "{rekey}"')
def add_rekey_to_address(context, rekey):
    context.txn.rekey_to = rekey


@given('base64 encoded data to sign "{data_enc}"')
def set_base64_encoded_data(context, data_enc):
    context.data = base64.b64decode(data_enc)


@given('program hash "{contract_addr}"')
def set_program_hash(context, contract_addr):
    context.address = contract_addr


@when("I perform tealsign")
def perform_tealsign(context):
    context.sig = logic.teal_sign(context.sk, context.data, context.address)


@then('the signature should be equal to "{sig_enc}"')
def check_tealsign(context, sig_enc):
    expected = base64.b64decode(sig_enc)
    assert expected == context.sig


@given('base64 encoded program "{program_enc}"')
def set_program_hash_from_program(context, program_enc):
    program = base64.b64decode(program_enc)
    context.address = logic.address(program)


@given('base64 encoded private key "{sk_enc}"')
def set_sk_from_encoded_seed(context, sk_enc):
    seed = base64.b64decode(sk_enc)
    key = SigningKey(seed)
    private_key = base64.b64encode(
        key.encode() + key.verify_key.encode()
    ).decode()
    context.sk = private_key


@then("fee field is in txn")
def fee_in_txn(context):
    if "signed_transaction" in context:
        stxn = context.signed_transaction.dictify()
    else:
        stxn = context.mtx.dictify()

    assert "fee" in stxn["txn"]


@then("fee field not in txn")
def fee_not_in_txn(context):
    if "signed_transaction" in context:
        stxn = context.signed_transaction.dictify()
    else:
        stxn = context.mtx.dictify()
    assert "fee" not in stxn["txn"]


def buildTxn(t, sender, params):
    txn = None
    if "online" in t:
        votekey = "9mr13Ri8rFepxN3ghIUrZNui6LqqM5hEzB45Rri5lkU="
        selkey = "dx717L3uOIIb/jr9OIyls1l5Ei00NFgRa380w7TnPr4="
        votefst = 0
        votelst = 2000
        votekd = 10
        sprf = "mYR0GVEObMTSNdsKM6RwYywHYPqVDqg3E4JFzxZOreH9NU8B+tKzUanyY8AQ144hETgSMX7fXWwjBdHz6AWk9w=="
        txn = transaction.KeyregOnlineTxn(
            sender,
            params,
            votekey,
            selkey,
            votefst,
            votelst,
            votekd,
            sprfkey=sprf,
        )
    elif "offline" in t:
        txn = transaction.KeyregOfflineTxn(sender, params)
    elif "nonparticipation" in t:
        txn = transaction.KeyregNonparticipatingTxn(sender, params)
    return txn


@given(
    'a base64 encoded program bytes for heuristic sanity check "{b64encoded:MaybeString}"'
)
def take_b64_encoded_bytes(context, b64encoded):
    context.seemingly_program = base64.b64decode(b64encoded)


@when("I start heuristic sanity check over the bytes")
def heuristic_check_over_bytes(context):
    context.sanity_check_err = ""

    try:
        transaction.LogicSigAccount(context.seemingly_program)
    except Exception as e:
        context.sanity_check_err = str(e)


@then(
    'if the heuristic sanity check throws an error, the error contains "{err_msg:MaybeString}"'
)
def check_error_if_matching(context, err_msg: str = None):
    if len(err_msg) > 0:
        assert err_msg in context.sanity_check_err
    else:
        assert len(context.sanity_check_err) == 0
