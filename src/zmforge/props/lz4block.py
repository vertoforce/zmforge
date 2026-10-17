"""One raw LZ4 block, compressed exactly as the BO3 mod tools compress it.

WHY [measured]: ``export2bin.exe`` wraps each ``.XMODEL_BIN``
payload in one LZ4 block.  Any valid block decodes to the same payload, but
the file only matches the Windows tools' output byte for byte if the match
finder is the same one.  Built from the LZ4 git tags and run over 40 kit
binaries the Windows tools' export2bin writes: r129, r130 and r131 (2015)
``LZ4_compress_default`` on a 64-bit build reproduced all 40 files; every
1.7.x to 1.10.0 build reproduced 9, and python-lz4 4.4.5 28.  This is
r131's ``LZ4_compress_generic`` (no dictionary, output not limited,
acceleration 1) in Python, so the conversion needs no compiled library.

What makes r131 differ from current LZ4: on a 64-bit build it hashes an
8-byte read times ``prime5bytes`` for both table types, where newer releases
use a 4-byte hash for inputs under 64 KB.
"""

# Ported from LZ4 r131, lib/lz4.c (https://github.com/lz4/lz4/blob/r131/lib/lz4.c).
# LZ4 - Fast LZ compression algorithm. Copyright (C) 2011-2015, Yann Collet.
# BSD 2-Clause License; the full notice is in THIRD_PARTY.md at the repository root.

from __future__ import annotations

__all__ = ["compress"]

_MINMATCH = 4
_LASTLITERALS = 5
_MFLIMIT = 12                  # COPYLENGTH (8) + MINMATCH
_MIN_LENGTH = _MFLIMIT + 1
_HASHLOG = 12                  # LZ4_MEMORY_USAGE (14) - 2
_LIMIT_64K = 64 * 1024 + _MFLIMIT - 1
_SKIP_TRIGGER = 6
_MAX_DISTANCE = 65535
_PRIME5 = 889523592379
_MASK64 = (1 << 64) - 1


def _count(src: bytes, a: int, b: int, limit: int) -> int:
    """Bytes equal at ``src[a:]`` and ``src[b:]`` before *limit* (for ``a``)."""
    n = 0
    step = 64
    while a + n < limit:
        k = min(step, limit - a - n)
        if src[a + n:a + n + k] == src[b + n:b + n + k]:
            n += k
            continue
        while k > 1:           # halve down to the first differing byte
            k //= 2
            if src[a + n:a + n + k] == src[b + n:b + n + k]:
                n += k
        if a + n < limit and src[a + n] == src[b + n]:
            n += 1
        return n
    return n


def _length_bytes(out: bytearray, rest: int) -> None:
    while rest >= 255:
        out.append(255)
        rest -= 255
    out.append(rest)


def compress(src: bytes) -> bytes:
    """*src* as one raw LZ4 block, as LZ4 r131 ``LZ4_compress_default`` (64-bit) writes it."""
    n = len(src)
    out = bytearray()
    anchor = 0
    if n >= _MIN_LENGTH:
        hashlog = _HASHLOG + 1 if n < _LIMIT_64K else _HASHLOG
        shift, mask = 40 - hashlog, (1 << hashlog) - 1
        check_distance = n >= _LIMIT_64K
        table = [0] * (1 << hashlog)
        mflimit, matchlimit = n - _MFLIMIT, n - _LASTLITERALS
        frombytes = int.from_bytes

        def hash_at(p: int) -> int:
            return (((frombytes(src[p:p + 8], "little") * _PRIME5) & _MASK64) >> shift) & mask

        table[hash_at(0)] = 0
        ip = 1
        forward_h = hash_at(ip)
        while True:
            # Find a match.
            forward_ip, step, search = ip, 1, 1 << _SKIP_TRIGGER
            while True:
                h = forward_h
                ip = forward_ip
                forward_ip += step
                step = search >> _SKIP_TRIGGER
                search += 1
                if forward_ip > mflimit:
                    break
                match = table[h]
                forward_h = hash_at(forward_ip)
                table[h] = ip
                if check_distance and match + _MAX_DISTANCE < ip:
                    continue
                if src[match:match + 4] == src[ip:ip + 4]:
                    break
            if forward_ip > mflimit:
                break
            # Catch up.
            while ip > anchor and match > 0 and src[ip - 1] == src[match - 1]:
                ip -= 1
                match -= 1
            lit = ip - anchor
            token_at = len(out)
            if lit >= 15:
                out.append(15 << 4)
                _length_bytes(out, lit - 15)
            else:
                out.append(lit << 4)
            out += src[anchor:ip]
            while True:
                # Offset and match length.
                off = ip - match
                out += bytes((off & 0xFF, off >> 8))
                mlen = _count(src, ip + _MINMATCH, match + _MINMATCH, matchlimit)
                ip += _MINMATCH + mlen
                if mlen >= 15:
                    out[token_at] += 15
                    rest = mlen - 15
                    while rest >= 510:
                        out += b"\xff\xff"
                        rest -= 510
                    if rest >= 255:
                        out.append(255)
                        rest -= 255
                    out.append(rest)
                else:
                    out[token_at] += mlen
                anchor = ip
                if ip > mflimit:
                    break
                table[hash_at(ip - 2)] = ip - 2
                h = hash_at(ip)
                match = table[h]
                table[h] = ip
                if match + _MAX_DISTANCE >= ip and src[match:match + 4] == src[ip:ip + 4]:
                    token_at = len(out)
                    out.append(0)
                    continue
                break
            if ip > mflimit:
                break
            ip += 1
            forward_h = hash_at(ip)
    last = n - anchor
    if last >= 15:
        out.append(15 << 4)
        _length_bytes(out, last - 15)
    else:
        out.append(last << 4)
    out += src[anchor:]
    return bytes(out)
