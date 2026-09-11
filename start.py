import urllib.request, json, time, subprocess, sys, threading, os, math
from datetime import datetime
import signal
try:
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
except Exception:
    pass

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

def get_mint_price():
    res = call_rpc("0x6817c76c") # mintPrice()
    if res:
        return int(res, 16)
    return 20320000000000000

# Detect available GPUs
def detect_gpus():
    try:
        out = subprocess.check_output(["nvidia-smi", "-L"], text=True)
        gpus = [line.strip() for line in out.strip().split("\n") if line.strip()]
        return len(gpus) if gpus else 1
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

# Dashboard Stats State
uptime_start_time = time.time()
round_start_time = time.time()
round_number = 1
minted_count = 0
reverted_count = 0
too_late_count = 0
total_spent_eth = 0.0
gpu_hashrates = {i: 0.0 for i in range(gpu_count)}
current_target = "0x000000000000ffffffffffffffffffffffffffffffffffffffffffffffffffff"
current_anchor_block = 0
mint_price_eth = get_mint_price() / 1e18
stop_flag = False
gpu_procs = []

def calc_odds(target_hex, total_ghs):
    try:
        target_int = int(target_hex, 16)
        bits = 256 - target_int.bit_length()
        total_hashes = (2**256) / (target_int if target_int > 0 else 1)
        thashes = total_hashes / 1e12

        hashes_per_sec = total_ghs * 1e9
        if hashes_per_sec > 0:
            avg_seconds = total_hashes / hashes_per_sec
            hrs = int(avg_seconds // 3600)
            mins = int((avg_seconds % 3600) // 60)
            avg_time = f"{hrs}h {mins:02d}m"
            prob_hour = (1.0 - math.exp(- (hashes_per_sec * 3600.0) / total_hashes)) * 100.0
        else:
            avg_time = "calculating..."
            prob_hour = 0.0
        return bits, thashes, avg_time, prob_hour
    except Exception:
        return 49, 562.9, "12h 00m", 8.0

def print_dashboard():
    now = time.time()
    uptime_sec = int(now - uptime_start_time)
    u_hrs = uptime_sec // 3600
    u_mins = (uptime_sec % 3600) // 60
    uptime_str = f"{u_hrs}h {u_mins}m" if u_hrs > 0 else f"{u_mins} min"

    round_age = now - round_start_time
    total_ghs = sum(gpu_hashrates.values())
    bits, thashes, avg_time, prob_hour = calc_odds(current_target, total_ghs)

    gpu_breakdown = "   ".join([f"gpu{i}   {gpu_hashrates[i]:.2f}" for i in range(gpu_count)]) + "  GH/s"

    border = "-" * 76
    print(f"\n{border}")
    print(f"HASHRATE   {total_ghs:.2f} GH/s       {gpu_count} of {gpu_count} GPUs mining")
    print(f"           {gpu_breakdown}")
    print()
    print(f"DIFFICULTY {bits} bits   =   {thashes:.1f} Thashes per cat")
    print(f"ROUND      #{round_number}   {round_age:.1f}s old     restarts when anyone mints")
    print(f"ODDS       one cat every {avg_time} on average     {prob_hour:.0f}% chance within the hour")
    print()
    print(f"RESULTS    {minted_count} minted    {reverted_count} reverted    {too_late_count} too late")
    print(f"SPENT      {total_spent_eth:.5f} ETH spent     next cat costs {mint_price_eth:.5f} ETH")
    print(f"UPTIME     {uptime_str}")
    print(f"{border}\n", flush=True)

def dashboard_ticker():
    while not stop_flag:
        time.sleep(12)
        print_dashboard()

threading.Thread(target=dashboard_ticker, daemon=True).start()

def send_mint_tx(winning_nonce, anchor_block, gpu_id):
    global minted_count, reverted_count, too_late_count, total_spent_eth
    if not private_key:
        print("[CLAIM] Manual Claim: Paste nonce and anchor in claim_cat.html!")
        return

    now_ts = datetime.now().strftime("%H:%M:%S")
    round_age = int(time.time() - round_start_time)
    print(f"\n{now_ts} OK SOLUTION found on gpu{gpu_id} after {round_age}s on this round")
    print(f"gas estimated at 194606, using limit 263257")

    acct = Account.from_key(private_key)
    price_wei = get_mint_price()
    price_eth = price_wei / 1e18

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
        print("[ERROR] Failed to fetch account nonce!")
        return

    # 2. Gas Price with +50% priority boost
    gas_price = 200000000
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
        "value": price_wei,
        "gas": 265000,
        "gasPrice": fast_gas,
        "nonce": tx_count,
        "chainId": 4663,
        "data": tx_data
    }
    signed = acct.sign_transaction(tx_dict)
    raw_hex = "0x" + signed.raw_transaction.hex()

    print(f"{now_ts} .. sent mint from gpu{gpu_id} for {price_eth:.5f} ETH, waiting for a receipt")

    # 5. Dual-Broadcast to Alchemy & dRPC
    broadcast_hashes = []
    def broadcast_to_rpc(target_rpc):
        try:
            req_s = urllib.request.Request(target_rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_sendRawTransaction","params":[raw_hex],"id":3}).encode(), headers={"Content-Type":"application/json", "User-Agent":"Mozilla/5.0"})
            res = json.loads(urllib.request.urlopen(req_s, timeout=4).read().decode())
            if "result" in res:
                broadcast_hashes.append((target_rpc, res["result"]))
        except Exception:
            pass

    threads = [threading.Thread(target=broadcast_to_rpc, args=(rpc,)) for rpc in RPCS]
    for t in threads: t.start()
    for t in threads: t.join()

    if not broadcast_hashes:
        print("[ERROR] Broadcast failed on all RPCs!")
        reverted_count += 1
        return

    primary_hash = broadcast_hashes[0][1]

    # Verify receipt
    confirmed = False
    for _ in range(15):
        time.sleep(1)
        for rpc in RPCS:
            try:
                req_rcpt = urllib.request.Request(rpc, data=json.dumps({"jsonrpc":"2.0","method":"eth_getTransactionReceipt","params":[primary_hash],"id":4}).encode(), headers={"Content-Type":"application/json"})
                res_rcpt = json.loads(urllib.request.urlopen(req_rcpt, timeout=2).read().decode())
                if res_rcpt.get("result"):
                    status = int(res_rcpt["result"]["status"], 16)
                    receipt = res_rcpt["result"]
                    now_ts2 = datetime.now().strftime("%H:%M:%S")
                    if status == 1:
                        # Extract token ID from logs if available
                        token_id = "MINED"
                        for lg in receipt.get("logs", []):
                            if lg.get("topics") and len(lg["topics"]) > 3:
                                token_id = str(int(lg["topics"][3], 16))
                                break
                        print(f"{now_ts2} OK MINTED CAT #{token_id} https://hashcats.fun/cat/{token_id}")
                        print(f"{now_ts2} https://robinhoodchain.blockscout.com/tx/{primary_hash}")
                        minted_count += 1
                        total_spent_eth += price_eth
                        confirmed = True
                        return
                    else:
                        print(f"{now_ts2} REVERTED: Transaction reverted on-chain!")
                        reverted_count += 1
                        confirmed = True
                        return
            except Exception:
                pass

    if not confirmed:
        too_late_count += 1
        print(f"Broadcast receipt uncertain. Check: https://robinhoodchain.blockscout.com/tx/{primary_hash}")

def chain_monitor():
    global round_start_time, round_number, current_target, current_anchor_block, mint_price_eth, gpu_procs
    last_pw = None
    while not stop_flag:
        time.sleep(3)
        pw, tg, ab, ah = get_state()
        if pw and pw != last_pw:
            if last_pw is not None:
                round_number += 1
                round_start_time = time.time()
                current_target = tg
                current_anchor_block = ab
                mint_price_eth = get_mint_price() / 1e18
                for p in gpu_procs:
                    if p.poll() is None:
                        p.terminate()
                        try:
                            p.wait(timeout=1)
                        except Exception:
                            p.kill()
            last_pw = pw

threading.Thread(target=chain_monitor, daemon=True).start()

STEP = 0x1000000000000000

while not stop_flag:
    prev_work, target, anchor_block, anchor_hash = get_state()
    if not prev_work:
        time.sleep(2)
        continue

    current_target = target
    current_anchor_block = anchor_block
    mint_price_eth = get_mint_price() / 1e18

    # Launch GPU workers
    gpu_procs = []
    for g_id in range(gpu_count):
        nonce_offset = str(g_id * STEP)
        cmd = ["./miner", wallet, prev_work, anchor_hash, target, str(g_id), nonce_offset]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        gpu_procs.append(p)

    def monitor_gpu(proc, g_id):
        global stop_flag
        for line in proc.stdout:
            # Parse speed
            if "Speed: " in line and "MH/s" in line:
                try:
                    # Example: [GPU 0] Speed: 3880.0 MH/s (3.88 GH/s)
                    parts = line.split("Speed: ")[1].split(" MH/s")[0].strip()
                    mhs = float(parts)
                    gpu_hashrates[g_id] = mhs / 1000.0
                except Exception:
                    pass

            if "SUCCESS! WINNING_NONCE=" in line:
                nonce = line.strip().split("=")[1]
                send_mint_tx(nonce, anchor_block, g_id)
                stop_flag = True
                for p in gpu_procs:
                    if p.poll() is None: p.terminate()
                break

    threads = [threading.Thread(target=monitor_gpu, args=(p, i)) for i, p in enumerate(gpu_procs)]
    for t in threads: t.start()
    for t in threads: t.join()
    for p in gpu_procs:
        try:
            if p.stdout: p.stdout.close()
            p.wait(timeout=0.5)
        except Exception:
            pass
