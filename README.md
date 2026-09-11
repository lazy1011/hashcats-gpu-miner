# Hashcats High-Speed GPU Miner

CUDA Keccak-256 GPU Miner for Hashcats on Robinhood Chain.

## Quickstart
```bash
git clone https://github.com/lazy1011/hashcats-gpu-miner.git
cd hashcats-gpu-miner
nvcc -O3 -arch=sm_89 miner.cu -o miner
python3 start.py 0xYOUR_METAMASK_ADDRESS
```
