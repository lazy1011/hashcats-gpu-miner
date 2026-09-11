#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <cuda_runtime.h>

__constant__ uint64_t RC[24] = {
    0x0000000000000001ULL, 0x0000000000008082ULL, 0x800000000000808aULL,
    0x8000000080008000ULL, 0x000000000000808bULL, 0x0000000080000001ULL,
    0x8000000080008081ULL, 0x8000000000008009ULL, 0x000000000000008aULL,
    0x0000000000000088ULL, 0x0000000080008009ULL, 0x000000008000000aULL,
    0x000000008000808bULL, 0x800000000000008bULL, 0x8000000000008089ULL,
    0x8000000000008003ULL, 0x8000000000008002ULL, 0x8000000000000080ULL,
    0x000000000000800aULL, 0x800000008000000aULL, 0x8000000080008081ULL,
    0x8000000000008080ULL, 0x0000000080000001ULL, 0x8000000080008008ULL
};

__constant__ int r[5][5] = {
    {0, 36, 3, 41, 18},
    {1, 44, 10, 45, 2},
    {62, 6, 43, 15, 61},
    {28, 55, 25, 21, 56},
    {27, 20, 39, 8, 14}
};

#define ROTL64(x, y) (((x) << (y)) | ((x) >> (64 - (y))))

__device__ void keccak_f1600(uint64_t A[5][5]) {
    for (int round_idx = 0; round_idx < 24; round_idx++) {
        uint64_t C[5], D[5];
        for (int x = 0; x < 5; x++)
            C[x] = A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4];
        for (int x = 0; x < 5; x++)
            D[x] = C[(x + 4) % 5] ^ ROTL64(C[(x + 1) % 5], 1);
        for (int x = 0; x < 5; x++)
            for (int y = 0; y < 5; y++)
                A[x][y] ^= D[x];

        uint64_t B[5][5];
        for (int x = 0; x < 5; x++)
            for (int y = 0; y < 5; y++)
                B[y][(2 * x + 3 * y) % 5] = ROTL64(A[x][y], r[x][y]);

        for (int x = 0; x < 5; x++)
            for (int y = 0; y < 5; y++)
                A[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y]);

        A[0][0] ^= RC[round_idx];
    }
}

__global__ void mine_kernel(
    const uint8_t* __restrict__ base_input, 
    uint64_t start_nonce, 
    uint64_t target_high, 
    uint64_t* d_found_nonce, 
    int* d_found
) {
    if (*d_found) return;
    uint64_t tid = blockDim.x * (uint64_t)blockIdx.x + threadIdx.x;
    uint64_t cur_nonce = start_nonce + tid;

    uint8_t input[136];
    #pragma unroll
    for (int i = 0; i < 136; i++) input[i] = base_input[i];

    // inject nonce (big-endian at bytes 44..51)
    #pragma unroll
    for (int i = 0; i < 8; i++) {
        input[44 + (7 - i)] = (uint8_t)((cur_nonce >> (i * 8)) & 0xFF);
    }

    uint64_t A[5][5] = {0};
    #pragma unroll
    for (int i = 0; i < 17; i++) {
        uint64_t w = 0;
        #pragma unroll
        for (int b = 0; b < 8; b++) {
            w |= ((uint64_t)input[8 * i + b]) << (8 * b);
        }
        A[i % 5][i / 5] = w;
    }

    keccak_f1600(A);

    // Byte-swap first 64-bit word of hash to big-endian
    uint64_t h0 = A[0][0];
    uint64_t h0_be = 0;
    #pragma unroll
    for (int b = 0; b < 8; b++) {
        h0_be |= ((h0 >> (8 * b)) & 0xFFULL) << (8 * (7 - b));
    }

    if (h0_be < target_high) {
        *d_found = 1;
        *d_found_nonce = cur_nonce;
    }
}

int main(int argc, char** argv) {
    if (argc < 5) {
        printf("Usage: ./miner <wallet_hex> <prev_work_hex> <anchor_hash_hex> <target_hex>\n");
        return 1;
    }

    uint8_t base_input[136] = {0};
    for (int i = 0; i < 20; i++) sscanf(argv[1] + 2 + 2*i, "%02hhx", &base_input[i]);
    for (int i = 0; i < 32; i++) sscanf(argv[2] + 2 + 2*i, "%02hhx", &base_input[52+i]);
    for (int i = 0; i < 32; i++) sscanf(argv[3] + 2 + 2*i, "%02hhx", &base_input[84+i]);
    base_input[116] = 0x01;
    base_input[135] = 0x80;

    uint64_t target_high = 0;
    sscanf(argv[4] + 2, "%16llx", (unsigned long long*)&target_high);

    uint8_t *d_input;
    uint64_t *d_found_nonce;
    int *d_found;
    cudaMalloc(&d_input, 136);
    cudaMalloc(&d_found_nonce, sizeof(uint64_t));
    cudaMalloc(&d_found, sizeof(int));

    cudaMemcpy(d_input, base_input, 136, cudaMemcpyHostToDevice);
    int zero = 0;
    cudaMemcpy(d_found, &zero, sizeof(int), cudaMemcpyHostToDevice);

    // Optimized for maximum GPU occupancy without register spill:
    // 256 threads per block, 4096 blocks = 1,048,576 threads per batch
    int threads = 256;
    int blocks = 4096;
    uint64_t batch_size = (uint64_t)threads * blocks;
    uint64_t start_nonce = ((uint64_t)time(NULL) ^ ((uint64_t)clock() << 16)) * 100000ULL;

    printf("[GPU] CUDA Keccak-256 Initialized. Target: 0x%016llx\n", (unsigned long long)target_high);
    printf("[GPU] Search Batch: %llu threads | Threads/Block: %d\n", (unsigned long long)batch_size, threads);

    int found = 0;
    uint64_t total_hashes = 0;
    clock_t t0 = clock();

    while (!found) {
        mine_kernel<<<blocks, threads>>>(d_input, start_nonce, target_high, d_found_nonce, d_found);
        
        cudaError_t err = cudaGetLastError();
        if (err != cudaSuccess) {
            printf("[FATAL] CUDA Launch Error: %s\n", cudaGetErrorString(err));
            return 1;
        }

        cudaMemcpy(&found, d_found, sizeof(int), cudaMemcpyDeviceToHost);
        start_nonce += batch_size;
        total_hashes += batch_size;

        if (total_hashes % (batch_size * 50) == 0) {
            clock_t t1 = clock();
            double sec = (double)(t1 - t0) / CLOCKS_PER_SEC;
            double mhs = (total_hashes / (sec > 0 ? sec : 0.001)) / 1000000.0;
            printf("[GPU] Real Speed: %.1f MH/s | Hashes: %llu\n", mhs, (unsigned long long)total_hashes);
        }
    }

    uint64_t winning_nonce = 0;
    cudaMemcpy(&winning_nonce, d_found_nonce, sizeof(uint64_t), cudaMemcpyDeviceToHost);
    printf("SUCCESS! WINNING_NONCE=%llu\n", (unsigned long long)winning_nonce);
    return 0;
}
