"""SM4 block cipher (GB/T 32907-2016) with CBC mode and PKCS#7 padding.

Pure-python implementation with the exact same semantics as the PHP runtime
embedded in the generated webshell, so both ends derive identical ciphertext.

Conventions
-----------
* key / iv are 16 raw bytes (bytes, bytearray or str -> utf-8 encoded)
* plaintext is PKCS#7 padded before encryption, padding is stripped after
  decryption
* all block operations are big-endian 32 bit words
"""

from __future__ import annotations

import os
import struct
from typing import Union

BytesLike = Union[bytes, bytearray, memoryview]

__all__ = [
    "SM4Error",
    "sm4_encrypt_block",
    "sm4_decrypt_block",
    "cbc_encrypt",
    "cbc_decrypt",
    "encrypt",
    "decrypt",
    "random_key",
    "random_iv",
    "pkcs7_pad",
    "pkcs7_unpad",
    "BLOCK_SIZE",
]

BLOCK_SIZE = 16

_FK = (0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC)

_SBOX = (
    0xd6, 0x90, 0xe9, 0xfe, 0xcc, 0xe1, 0x3d, 0xb7, 0x16, 0xb6, 0x14, 0xc2, 0x28, 0xfb, 0x2c, 0x05,
    0x2b, 0x67, 0x9a, 0x76, 0x2a, 0xbe, 0x04, 0xc3, 0xaa, 0x44, 0x13, 0x26, 0x49, 0x86, 0x06, 0x99,
    0x9c, 0x42, 0x50, 0xf4, 0x91, 0xef, 0x98, 0x7a, 0x33, 0x54, 0x0b, 0x43, 0xed, 0xcf, 0xac, 0x62,
    0xe4, 0xb3, 0x1c, 0xa9, 0xc9, 0x08, 0xe8, 0x95, 0x80, 0xdf, 0x94, 0xfa, 0x75, 0x8f, 0x3f, 0xa6,
    0x47, 0x07, 0xa7, 0xfc, 0xf3, 0x73, 0x17, 0xba, 0x83, 0x59, 0x3c, 0x19, 0xe6, 0x85, 0x4f, 0xa8,
    0x68, 0x6b, 0x81, 0xb2, 0x71, 0x64, 0xda, 0x8b, 0xf8, 0xeb, 0x0f, 0x4b, 0x70, 0x56, 0x9d, 0x35,
    0x1e, 0x24, 0x0e, 0x5e, 0x63, 0x58, 0xd1, 0xa2, 0x25, 0x22, 0x7c, 0x3b, 0x01, 0x21, 0x78, 0x87,
    0xd4, 0x00, 0x46, 0x57, 0x9f, 0xd3, 0x27, 0x52, 0x4c, 0x36, 0x02, 0xe7, 0xa0, 0xc4, 0xc8, 0x9e,
    0xea, 0xbf, 0x8a, 0xd2, 0x40, 0xc7, 0x38, 0xb5, 0xa3, 0xf7, 0xf2, 0xce, 0xf9, 0x61, 0x15, 0xa1,
    0xe0, 0xae, 0x5d, 0xa4, 0x9b, 0x34, 0x1a, 0x55, 0xad, 0x93, 0x32, 0x30, 0xf5, 0x8c, 0xb1, 0xe3,
    0x1d, 0xf6, 0xe2, 0x2e, 0x82, 0x66, 0xca, 0x60, 0xc0, 0x29, 0x23, 0xab, 0x0d, 0x53, 0x4e, 0x6f,
    0xd5, 0xdb, 0x37, 0x45, 0xde, 0xfd, 0x8e, 0x2f, 0x03, 0xff, 0x6a, 0x72, 0x6d, 0x6c, 0x5b, 0x51,
    0x8d, 0x1b, 0xaf, 0x92, 0xbb, 0xdd, 0xbc, 0x7f, 0x11, 0xd9, 0x5c, 0x41, 0x1f, 0x10, 0x5a, 0xd8,
    0x0a, 0xc1, 0x31, 0x88, 0xa5, 0xcd, 0x7b, 0xbd, 0x2d, 0x74, 0xd0, 0x12, 0xb8, 0xe5, 0xb4, 0xb0,
    0x89, 0x69, 0x97, 0x4a, 0x0c, 0x96, 0x77, 0x7e, 0x65, 0xb9, 0xf1, 0x09, 0xc5, 0x6e, 0xc6, 0x84,
    0x18, 0xf0, 0x7d, 0xec, 0x3a, 0xdc, 0x4d, 0x20, 0x79, 0xee, 0x5f, 0x3e, 0xd7, 0xcb, 0x39, 0x48,
)

MASK32 = 0xFFFFFFFF

# SM4 rounds are cheap; precompute the two linear transforms as 4x256 tables so
# bulk traffic (file transfers) stays usable inside the interpreter.
_T_A = [[0] * 256 for _ in range(4)]
_T_A_INV = [[0] * 256 for _ in range(4)]


def _rotl(x: int, n: int) -> int:
    x &= MASK32
    return ((x << n) | (x >> (32 - n))) & MASK32


def _build_tables() -> None:
    # A byte placed in the most significant position contributes L(s << 24);
    # the byte at position p (0 = MSB) contributes rotl(L(s << 24), (4 - p) * 8).
    for i in range(256):
        s = _SBOX[i]
        b = (s << 24) & MASK32
        v = b ^ _rotl(b, 2) ^ _rotl(b, 10) ^ _rotl(b, 18) ^ _rotl(b, 24)
        # key-schedule linear transform L'(b) = b ^ rotl(b,13) ^ rotl(b,23)
        k = b ^ _rotl(b, 13) ^ _rotl(b, 23)
        for p in range(4):
            n = ((4 - p) * 8) % 32
            _T_A[p][i] = _rotl(v, n)
            _T_A_INV[p][i] = _rotl(k, n)


_build_tables()


class SM4Error(ValueError):
    """Raised for invalid key/iv/ciphertext input."""


def _as_bytes(value: BytesLike, name: str) -> bytes:
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise SM4Error(f"{name} must be bytes, got {type(value)!r}")
    return bytes(value)


def _key_words(key: BytesLike) -> tuple[int, int, int, int]:
    raw = _as_bytes(key, "key")
    if len(raw) != 16:
        raise SM4Error(f"SM4 key must be exactly 16 bytes, got {len(raw)}")
    return struct.unpack(">4I", raw)


def _round_keys(key: BytesLike) -> list[int]:
    k0, k1, k2, k3 = _key_words(key)
    k = [k0 ^ _FK[0], k1 ^ _FK[1], k2 ^ _FK[2], k3 ^ _FK[3]]
    rk = [0] * 32
    t0, t1, t2, t3 = _T_A_INV
    for i in range(32):
        ck = (
            ((4 * i + 0) * 7 % 256) << 24
            | ((4 * i + 1) * 7 % 256) << 16
            | ((4 * i + 2) * 7 % 256) << 8
            | ((4 * i + 3) * 7 % 256)
        )
        x = k[i + 1] ^ k[i + 2] ^ k[i + 3] ^ ck
        v = t0[x >> 24] ^ t1[(x >> 16) & 0xFF] ^ t2[(x >> 8) & 0xFF] ^ t3[x & 0xFF]
        k.append(k[i] ^ v)
        rk[i] = k[i + 4]
    return rk


def _crypt_block(block: bytes, rk: list[int]) -> bytes:
    x0, x1, x2, x3 = struct.unpack(">4I", block)
    t0, t1, t2, t3 = _T_A
    for i in range(32):
        x = x1 ^ x2 ^ x3 ^ rk[i]
        v = t0[x >> 24] ^ t1[(x >> 16) & 0xFF] ^ t2[(x >> 8) & 0xFF] ^ t3[x & 0xFF]
        x0, x1, x2, x3 = x1, x2, x3, x0 ^ v
    # output is the reverse word order
    return struct.pack(">4I", x3, x2, x1, x0)


def sm4_encrypt_block(block: bytes, key: BytesLike) -> bytes:
    """Encrypt a single 16 byte block."""
    block = _as_bytes(block, "block")
    if len(block) != BLOCK_SIZE:
        raise SM4Error(f"block must be 16 bytes, got {len(block)}")
    return _crypt_block(block, _round_keys(key))


def sm4_decrypt_block(block: bytes, key: BytesLike) -> bytes:
    """Decrypt a single 16 byte block."""
    block = _as_bytes(block, "block")
    if len(block) != BLOCK_SIZE:
        raise SM4Error(f"block must be 16 bytes, got {len(block)}")
    return _crypt_block(block, _round_keys(key)[::-1])


def pkcs7_pad(data: bytes) -> bytes:
    n = BLOCK_SIZE - (len(data) % BLOCK_SIZE)
    return data + bytes([n]) * n


def pkcs7_unpad(data: bytes) -> bytes:
    if not data or len(data) % BLOCK_SIZE:
        raise SM4Error("ciphertext length is not a multiple of the block size")
    n = data[-1]
    if not 1 <= n <= BLOCK_SIZE or data[-n:] != bytes([n]) * n:
        raise SM4Error("invalid PKCS#7 padding")
    return data[:-n]


def _as16(value: BytesLike, name: str) -> bytes:
    raw = _as_bytes(value, name)
    if len(raw) != 16:
        raise SM4Error(f"{name} must be exactly 16 bytes, got {len(raw)}")
    return raw


def cbc_encrypt(plaintext: BytesLike, key: BytesLike, iv: BytesLike) -> bytes:
    """SM4-CBC encrypt with PKCS#7 padding."""
    data = pkcs7_pad(_as_bytes(plaintext, "plaintext"))
    key = _as16(key, "key")
    iv = _as16(iv, "iv")
    rk = _round_keys(key)
    out = bytearray(len(data))
    prev = int.from_bytes(iv, "big")
    for off in range(0, len(data), BLOCK_SIZE):
        blk = int.from_bytes(data[off:off + BLOCK_SIZE], "big") ^ prev
        ct = _crypt_block(blk.to_bytes(BLOCK_SIZE, "big"), rk)
        out[off:off + BLOCK_SIZE] = ct
        prev = int.from_bytes(ct, "big")
    return bytes(out)


def cbc_decrypt(ciphertext: BytesLike, key: BytesLike, iv: BytesLike) -> bytes:
    """SM4-CBC decrypt and strip PKCS#7 padding."""
    data = _as_bytes(ciphertext, "ciphertext")
    if not data or len(data) % BLOCK_SIZE:
        raise SM4Error("ciphertext length is not a multiple of the block size")
    key = _as16(key, "key")
    iv = _as16(iv, "iv")
    rk = _round_keys(key)[::-1]
    out = bytearray(len(data))
    prev = int.from_bytes(iv, "big")
    for off in range(0, len(data), BLOCK_SIZE):
        ct = data[off:off + BLOCK_SIZE]
        blk = int.from_bytes(_crypt_block(ct, rk), "big") ^ prev
        out[off:off + BLOCK_SIZE] = blk.to_bytes(BLOCK_SIZE, "big")
        prev = int.from_bytes(ct, "big")
    return pkcs7_unpad(bytes(out))


# Short aliases used by the protocol layer.
def encrypt(plaintext: BytesLike, key: BytesLike, iv: BytesLike) -> bytes:
    return cbc_encrypt(plaintext, key, iv)


def decrypt(ciphertext: BytesLike, key: BytesLike, iv: BytesLike) -> bytes:
    return cbc_decrypt(ciphertext, key, iv)


def random_key() -> bytes:
    return os.urandom(16)


def random_iv() -> bytes:
    return os.urandom(16)
