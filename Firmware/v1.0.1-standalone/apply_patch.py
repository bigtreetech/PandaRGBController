#!/usr/bin/env python3
"""
Rebuild the standalone firmware from the official v1.0.1 image.

Run it against the stock Firmware/v1.0.1/panda_rgb_controller_v1.0.1.bin and it
produces the exact same standalone .bin (verify by sha256). The changes are a
handful of code/data bytes plus the recomputed ESP image checksum and SHA-256
trailer.

    python3 apply_patch.py ../v1.0.1/panda_rgb_controller_v1.0.1.bin out.bin

Change 1 - breathing (and any effect) without a printer
-------------------------------------------------------
In app_rgb.c the RGB task reads a display state from get_display_state(). That
function only returns "render the selected effect" while the printer MQTT link
is up (its connection global == 3). With no printer it falls through to a
default `return 0`, which the task renders as a hard blue strobe (effect index
2 = Strobing, colour #0000FF). That override sits on top of the on/off, follow
and warning toggles, so no setting can defeat it.

    get_display_state()  @ vaddr 0x4200a9f6  (file offset 0x4a9f6)
        before:  c.li a0, 0   bytes 01 45     -> no printer => blue strobe
        after:   c.li a0, 1   bytes 05 45     -> no printer => render selected effect

Change 2 - smoother, slower breathing
-------------------------------------
The breathing renderer keeps a phase that bounces 0..60 and steps it by
direction(+/-1.0) * 3.0 = +/-3.0 per frame, so a full breath is only ~40
brightness steps - visibly choppy, and it gets choppier the slower you set it.
The two direction constants are dropped from +/-1.0 to +/-0.2, so the step is
+/-0.6 and a breath is ~200 steps: ~5x finer (smoother) and ~5x longer (slower,
so the slow end of the speed slider now goes well below the old minimum). The
phase range (60) and the /100 brightness maths are untouched, so brightness and
colour are unchanged. These two constants are shared with the H2D printer status
fade, which gets the same slower/smoother timing - only visible with an H2D
printer connected.

    C_f8 @ 0x3c0e63f8 (file offset 0x63f8):  -1.0 -> -0.2   (00 00 80 bf -> cd cc 4c be)
    C_fc @ 0x3c0e63fc (file offset 0x63fc):  +1.0 -> +0.2   (00 00 80 3f -> cd cc 4c 3e)
"""
import sys, struct, hashlib

# (file_offset, expected_old_bytes, new_bytes)
PATCHES = [
    (0x4a9f6, bytes([0x01]),                 bytes([0x05])),                  # state 0 -> 1
    (0x63f8,  bytes.fromhex("000080bf"),     struct.pack("<f", -0.2)),        # C_f8 -1.0 -> -0.2
    (0x63fc,  bytes.fromhex("0000803f"),     struct.pack("<f",  0.2)),        # C_fc  1.0 ->  0.2
]

STOCK_SHA = "c12b74cd9541d95c8744d9f8169e84d7865bab40f16be56929bc860df920536f"
OUT_SHA   = "f58ffd02fec5f4e6f0f2c05c7d7e9b270622840845bace9acbcba79869d5309f"


def esp_image_trailer(d):
    """Return (segment_spans, checksum_offset, hash_offset) for an ESP32 app image."""
    seg_count = d[1]
    off = 24
    seg_spans = []
    for _ in range(seg_count):
        _load, ln = struct.unpack("<II", d[off:off + 8])
        off += 8
        seg_spans.append((off, ln))
        off += ln
    pad = (15 - (off % 16)) % 16
    cksum_off = off + pad
    return seg_spans, cksum_off, cksum_off + 1


def xor_checksum(d, seg_spans):
    c = 0xEF
    for fo, ln in seg_spans:
        for b in d[fo:fo + ln]:
            c ^= b
    return c & 0xFF


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        print("usage: python3 apply_patch.py <stock_v1.0.1.bin> <output.bin>")
        return 1

    src, dst = sys.argv[1], sys.argv[2]
    d = bytearray(open(src, "rb").read())

    got = hashlib.sha256(d).hexdigest()
    if got != STOCK_SHA:
        print(f"warning: input sha256 {got} does not match the known stock v1.0.1 "
              f"({STOCK_SHA}). continuing anyway.")

    for off, old, new in PATCHES:
        cur = bytes(d[off:off + len(old)])
        if cur != old:
            print(f"error: bytes at 0x{off:x} are {cur.hex()}, expected {old.hex()}. "
                  f"this is not the expected image.")
            return 1
        d[off:off + len(new)] = new

    seg_spans, cksum_off, hash_off = esp_image_trailer(d)
    d[cksum_off] = xor_checksum(d, seg_spans)
    d[hash_off:hash_off + 32] = hashlib.sha256(bytes(d[:hash_off])).digest()

    open(dst, "wb").write(d)
    out = hashlib.sha256(d).hexdigest()
    print(f"wrote {dst} ({len(d)} bytes)")
    print(f"sha256 {out}")
    print("sha256 matches expected standalone image" if out == OUT_SHA
          else f"note: sha256 differs from reference {OUT_SHA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
