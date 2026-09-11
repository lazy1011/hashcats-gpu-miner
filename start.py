import urllib.request, json, time, subprocess, sys, threading

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

wallet = sys.argv[1] if len(sys.argv) > 1 else input("Enter your MetaMask address: ").strip()

print("="*65)
print(f"🐱 HASHCATS HIGH-SPEED AUTO-SYNC MINER")
print(f"Target Wallet: {wallet}")
print("="*65)

current_proc = None
stop_flag = False

def chain_monitor():
    global current_proc, last_prev_work, stop_flag
    while not stop_flag:
        time.sleep(6)
        pw, tg, ab, ah = get_state()
        if pw and pw != last_prev_work:
            print(f"\n\n[CHAIN UPDATE] 🔔 Block advanced! Someone minted a cat.")
            print(f"[CHAIN UPDATE] Updating to new PrevWork: {pw[:18]}... Restarting GPU on fresh round!\n")
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
    print(f"\n>>> ROUND ACTIVE: Anchor #{anchor_block} | Target: {target[:18]}...")
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
            print("CLAIM NOW via your Claim App or https://hashcats.fun/mine !")
            print("="*65)
            stop_flag = True
            break

    if current_proc.poll() is None:
        current_proc.terminate()
