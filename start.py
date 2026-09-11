import urllib.request, json, time, subprocess, sys, threading, os

# Auto-install eth-account if missing
try:
    from eth_account import Account
except ImportError:
    print("[INIT] Installing eth-account for instant auto-minting...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "eth-account", "--quiet"])
    from eth_account import Account

# Primary: User Dedicated Alchemy RPC (Sub-50ms latency)
# Secondary: dRPC Fallback
RPCS = [
    "https://robinhood-mainnet.g.alchemy.com/v2/2mLwK8sr1SFmCGYugLzKPkrpEu0c5-s4",
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
            res = json.loads(urllib.request.urlopen(req, timeout=3).read().decode())
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

# Detect available GPUs
def detect_gpus():
    try:
        out = subprocess.check_output(["nvidia-smi", "-L"], text=True)
        gpus = [line.strip() for line in out.strip().split("\n") if line.strip()]
        return len(gpus)
    except Exception:
        return 1

gpu_count = detect_gpus()

# Parse input
user_arg = sys.argv[1] if len(sys.argv) > 1 else input("Enter Burner Private Key or Wallet Address: ").strip()

private_key = None
if len(user_arg.replace("0x", "")) == 64:
    private_key = user_arg if user_arg.startswith("0x") else "0x" + user_arg
    acct = Account.from_key(private_key)
    wallet = acct.address
    auto_mint = True
else:
    wallet = user_arg
    auto_mint = False

print("="*65)
print("🐱 HASHCATS HIGH-SPEED PRO MINER (MULTI-GPU + DEDICATED RPC)")
print(f"Target Wallet: {wallet}")
print(f"GPUs Detected: {gpu_count} GPU(s)")
print(f"Primary RPC:   Alchemy Dedicated High-Speed Node")
print(f"Mode:          {'🚀 AUTO-MINT ENABLED (Multi-RPC Parallel Broadcast)' if auto_mint else '📝 MANUAL CLAIM'}")
print("="*65)

def send_mint_tx(winning_nonce, anchor_block):
    if not private_key:
        return
    print("\n" + "="*65)
    print("⚡⚡⚡ [AUTO-MINT TRIGGERED] Broadcasting transaction NOW! ⚡⚡⚡")
    acct = Account.from_key(private_key)
    
    # 1. Nonce from Alchemy
    tx_count = None
    for rpc in RPCS:
        try:
            req_n = urllib.request.Request(rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_getTransactionCount","params":[acct.address, "latest"],"id":1}).encode(), headers={"Content-Type":"application/json", "User-Agent":"Mozilla/5.0"})
            res_n = json.loads(urllib.request.urlopen(req_n, timeout=3).read().decode())
            if "result" in res_n:
                tx_count = int(res_n["result"], 16)
                break
        except Exception:
            continue
            
    if tx_count is None:
        print("[ERROR] Failed to fetch wallet nonce from RPCs!")
        return

    # 2. Gas Price with 50% priority boost for instant block inclusion
    gas_price = 200000000 # default 0.2 Gwei
    for rpc in RPCS:
        try:
            req_g = urllib.request.Request(rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_gasPrice","params":[],"id":2}).encode(), headers={"Content-Type":"application/json", "User-Agent":"Mozilla/5.0"})
            res_g = json.loads(urllib.request.urlopen(req_g, timeout=3).read().decode())
            if "result" in res_g:
                gas_price = int(res_g["result"], 16)
                break
        except Exception:
            continue
    fast_gas = int(gas_price * 1.50)

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

    # 5. Parallel Multi-RPC Broadcast (Simultaneously fire to Alchemy + dRPC)
    broadcast_hashes = []
    def broadcast_to_rpc(target_rpc):
        try:
            req_s = urllib.request.Request(target_rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_sendRawTransaction","params":[raw_hex],"id":3}).encode(), headers={"Content-Type":"application/json", "User-Agent":"Mozilla/5.0"})
            res = json.loads(urllib.request.urlopen(req_s, timeout=4).read().decode())
            if "result" in res:
                broadcast_hashes.append((target_rpc, res["result"]))
        except Exception as e:
            pass

    threads = [threading.Thread(target=broadcast_to_rpc, args=(rpc,)) for rpc in RPCS]
    for t in threads: t.start()
    for t in threads: t.join()

    if broadcast_hashes:
        primary_hash = broadcast_hashes[0][1]
        print(f"\n🎉🎉🎉 SUCCESS! TRANSACTION BROADCAST ON-CHAIN! 🎉🎉🎉")
        print(f"Tx Hash: {primary_hash}")
        print(f"Broadcasted to {len(broadcast_hashes)} RPC endpoints simultaneously.")
        print(f"Track: https://robinhoodchain.blockscout.com/tx/{primary_hash}")
        print("="*65)
        
        # Verify receipt
        print("[VERIFY] Waiting for block confirmation...")
        for _ in range(15):
            time.sleep(1)
            for rpc in RPCS:
                try:
                    req_rcpt = urllib.request.Request(rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_getTransactionReceipt","params":[primary_hash],"id":4}).encode(), headers={"Content-Type":"application/json"})
                    res_rcpt = json.loads(urllib.request.urlopen(req_rcpt, timeout=2).read().decode())
                    if res_rcpt.get("result"):
                        status = int(res_rcpt["result"]["status"], 16)
                        if status == 1:
                            print(f"\n💎💎💎 MINT CONFIRMED IN BLOCK #{int(res_rcpt['result']['blockNumber'], 16)}! CONGRATULATIONS! 💎💎💎\n")
                            return
                except Exception:
                    pass
    else:
        print("[ERROR] All broadcast attempts failed! Check balance/gas.")

gpu_procs = []
stop_flag = False

def chain_monitor():
    global last_prev_work, stop_flag, gpu_procs
    while not stop_flag:
        time.sleep(4)
        pw, tg, ab, ah = get_state()
        if pw and pw != last_prev_work:
            print(f"\n[CHAIN UPDATE] 🔔 Block advanced! Someone minted. Restarting GPU rounds...")
            for p in gpu_procs:
                if p.poll() is None:
                    p.terminate()

last_prev_work = None
threading.Thread(target=chain_monitor, daemon=True).start()

# Partition space across GPUs
STEP = 0x1000000000000000

while not stop_flag:
    prev_work, target, anchor_block, anchor_hash = get_state()
    if not prev_work:
        time.sleep(2)
        continue

    last_prev_work = prev_work
    print(f"\n>>> ACTIVE ROUND: Anchor #{anchor_block} | Target: {target[:18]}...")
    print(f">>> PrevWork: {prev_work[:18]}...")
    print(f">>> Launching {gpu_count} GPU worker(s) across partitioned nonces...")

    gpu_procs = []
    for g_id in range(gpu_count):
        nonce_offset = str(g_id * STEP)
        cmd = ["./miner", wallet, prev_work, anchor_hash, target, str(g_id), nonce_offset]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        gpu_procs.append(p)

    def monitor_gpu(proc, g_id):
        global stop_flag
        for line in proc.stdout:
            print(line, end="", flush=True)
            if "SUCCESS! WINNING_NONCE=" in line:
                nonce = line.strip().split("=")[1]
                print("\n" + "="*65)
                print(f"🎉🎉🎉 BINGO! GPU {g_id} FOUND WINNING NONCE! 🎉🎉🎉")
                print(f"Winning Nonce: {nonce}")
                print(f"Anchor Block:  {anchor_block}")
                
                if auto_mint:
                    send_mint_tx(nonce, anchor_block)
                else:
                    print("Claim on https://hashcats.fun/mine or your local claim app!")
                print("="*65)
                stop_flag = True
                for p in gpu_procs:
                    if p.poll() is None: p.terminate()
                break

    threads = [threading.Thread(target=monitor_gpu, args=(p, i)) for i, p in enumerate(gpu_procs)]
    for t in threads: t.start()
    for t in threads: t.join()
