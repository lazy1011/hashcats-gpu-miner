import urllib.request, json, time, subprocess, sys, threading, os

# Auto-install eth-account if missing
try:
    from eth_account import Account
except ImportError:
    print("[INIT] Installing eth-account for instant auto-minting...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "eth-account", "--quiet"])
    from eth_account import Account

RPCS = [
    "https://rpc.mainnet.chain.robinhood.com",
    "https://robinhood.drpc.org"
]
CONTRACT = "0xCA75DF55Cc9C476DB27a7375D1fc8E794cf80721"

def call_rpc(data_hex):
    for rpc in RPCS:
        try:
            req = urllib.request.Request(
                rpc,
                data=json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to": CONTRACT, "data": data_hex}, "latest"],"id":1}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            )
            res = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
            if "result" in res and res["result"] != "0x":
                return res["result"]
        except Exception:
            continue
    return None

def get_state():
    prev_work = call_rpc("0xa4da5da2")
    target = call_rpc("0x39148c53")
    anchor = call_rpc("0xcd809b11")
    if not (prev_work and target and anchor):
        return None, None, None, None
    anchor_block = int(anchor[2:66], 16)
    anchor_hash = "0x" + anchor[66:130]
    return prev_work, target, anchor_block, anchor_hash

# Parse input
user_arg = sys.argv[1] if len(sys.argv) > 1 else input("Enter Burner Private Key or Wallet Address: ").strip()

private_key = None
if len(user_arg.replace("0x", "")) == 64:
    # Private Key provided -> AUTO-MINT MODE!
    private_key = user_arg if user_arg.startswith("0x") else "0x" + user_arg
    acct = Account.from_key(private_key)
    wallet = acct.address
    auto_mint = True
else:
    wallet = user_arg
    auto_mint = False

print("="*65)
print(f"🐱 HASHCATS HIGH-SPEED GPU MINER")
print(f"Target Wallet: {wallet}")
print(f"Mode:          {'🚀 AUTO-MINT ENABLED (0.001s Instant Submit)' if auto_mint else '📝 MANUAL CLAIM'}")
print("="*65)

def send_mint_tx(winning_nonce, anchor_block):
    if not private_key:
        return
    print("\n" + "="*65)
    print("⚡⚡⚡ [AUTO-MINT TRIGGERED] Broadcasting transaction NOW! ⚡⚡⚡")
    acct = Account.from_key(private_key)
    
    rpc = RPCS[0]
    # 1. Nonce
    req_n = urllib.request.Request(rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_getTransactionCount","params":[acct.address, "latest"],"id":1}).encode(), headers={"Content-Type":"application/json"})
    tx_count = int(json.loads(urllib.request.urlopen(req_n).read().decode())["result"], 16)

    # 2. Gas Price with 35% boost for fast inclusion
    req_g = urllib.request.Request(rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_gasPrice","params":[],"id":2}).encode(), headers={"Content-Type":"application/json"})
    gas_price = int(json.loads(urllib.request.urlopen(req_g).read().decode())["result"], 16)
    fast_gas = int(gas_price * 1.35)

    # 3. Payload: mine(uint256 nonce, uint256 anchorBlock)
    tx_data = f"0x071e9503{int(winning_nonce):064x}{int(anchor_block):064x}"

    # 4. Sign raw tx
    tx_dict = {
        "to": CONTRACT,
        "value": 10080000000000000, # 0.01008 ETH
        "gas": 450000,
        "gasPrice": fast_gas,
        "nonce": tx_count,
        "chainId": 4663,
        "data": tx_data
    }
    signed = acct.sign_transaction(tx_dict)
    raw_hex = "0x" + signed.raw_transaction.hex()

    # 5. Broadcast
    req_s = urllib.request.Request(rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_sendRawTransaction","params":[raw_hex],"id":3}).encode(), headers={"Content-Type":"application/json"})
    res = json.loads(urllib.request.urlopen(req_s).read().decode())
    
    if "result" in res:
        tx_hash = res["result"]
        print(f"\n🎉🎉🎉 SUCCESS! TRANSACTION BROADCAST TO BLOCKCHAIN! 🎉🎉🎉")
        print(f"Tx Hash: {tx_hash}")
        print(f"Track on Explorer: https://explorer.mainnet.chain.robinhood.com/tx/{tx_hash}")
        print("="*65)
    else:
        print(f"[ERROR] Broadcast failed: {res.get('error')}")

current_proc = None
stop_flag = False

def chain_monitor():
    global current_proc, last_prev_work, stop_flag
    while not stop_flag:
        time.sleep(5)
        pw, tg, ab, ah = get_state()
        if pw and pw != last_prev_work:
            print(f"\n[CHAIN UPDATE] 🔔 Block advanced! Round restarting...")
            if current_proc and current_proc.poll() is None:
                current_proc.terminate()

last_prev_work = None
threading.Thread(target=chain_monitor, daemon=True).start()

while not stop_flag:
    prev_work, target, anchor_block, anchor_hash = get_state()
    if not prev_work:
        time.sleep(2)
        continue

    last_prev_work = prev_work
    print(f"\n>>> ACTIVE ROUND: Anchor #{anchor_block} | Target: {target[:18]}...")
    print(f">>> PrevWork: {prev_work[:18]}...")
    print(">>> Mining at full GPU power...")

    cmd = ["./miner", wallet, prev_work, anchor_hash, target]
    current_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    for line in current_proc.stdout:
        print(line, end="", flush=True)
        if "SUCCESS! WINNING_NONCE=" in line:
            nonce = line.strip().split("=")[1]
            print("\n" + "="*65)
            print("🎉🎉🎉 BINGO! WINNING NONCE FOUND! 🎉🎉🎉")
            print(f"Winning Nonce: {nonce}")
            print(f"Anchor Block:  {anchor_block}")
            
            if auto_mint:
                send_mint_tx(nonce, anchor_block)
            else:
                print("Claim on https://hashcats.fun/mine or your local claim app!")
            print("="*65)
            stop_flag = True
            break

    if current_proc.poll() is None:
        current_proc.terminate()
