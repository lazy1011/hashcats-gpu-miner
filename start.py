import urllib.request, json, time, subprocess, sys

RPC = "https://rpc.mainnet.chain.robinhood.com"
CONTRACT = "0xCA75DF55Cc9C476DB27a7375D1fc8E794cf80721"

def call_rpc(data_hex):
    req = urllib.request.Request(
        RPC,
        data=json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to": CONTRACT, "data": data_hex}, "latest"],"id":1}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    res = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
    return res.get("result")

wallet = sys.argv[1] if len(sys.argv) > 1 else input("Enter your MetaMask address: ").strip()

print("="*60)
print(f"🐱 HASHCATS HIGH-SPEED GPU MINER (RTX 6000 Ada)")
print(f"Target Wallet: {wallet}")
print("="*60)

prev_work = call_rpc("0x5996c56b")
target = call_rpc("0xe00ad99c")
anchor = call_rpc("0x82dbd7e9")
anchor_block = int(anchor[2:66], 16)
anchor_hash = "0x" + anchor[66:130]

print(f"Anchor Block: {anchor_block}")
print(f"Anchor Hash:  {anchor_hash}")
print(f"Target:       {target}")
print(f"Prev Work:    {prev_work}")
print("="*60)
print("Starting RTX 6000 Ada CUDA Engine...")

cmd = ["./miner", wallet, prev_work, anchor_hash, target]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

for line in proc.stdout:
    print(line, end="", flush=True)
    if "SUCCESS! WINNING_NONCE=" in line:
        nonce = line.strip().split("=")[1]
        print("\n" + "="*60)
        print("🎉🎉🎉 BINGO! WINNING NONCE FOUND! 🎉🎉🎉")
        print(f"Winning Nonce: {nonce}")
        print(f"Anchor Block:  {anchor_block}")
        print(f"Go to https://hashcats.fun/mine to claim, or submit via MetaMask!")
        print("="*60)
        break
