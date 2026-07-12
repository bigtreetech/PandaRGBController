#!/usr/bin/env python3
"""
Rebuild the standalone-breathing firmware from the official v1.0.1 image.

Run it against the stock Firmware/v1.0.1/panda_rgb_controller_v1.0.1.bin and it
produces the exact same standalone .bin (verify by sha256). The only change is a
single code byte plus the recomputed ESP image checksum and SHA-256 trailer.

    python3 apply_patch.py ../v1.0.1/panda_rgb_controller_v1.0.1.bin out.bin

What it changes
---------------
In app_rgb.c the RGB task reads a display state from get_display_state(). That
function only returns "state 1" (render the user-selected effect) while the
printer MQTT link is up (its connection global == 3). With no printer it falls
through to its default `return 0`, which the task renders as a hard blue strobe
(effect index 2 = Strobing, colour #0000FF). That override sits on top of the
on/off, follow and warning toggles, so no setting can defeat it.

The patch flips that default from 0 to 1, so a disconnected controller renders
the selected effect (breathing, static, etc.) instead of the blue strobe. It
routes through the normal path, so it still honours the follow / current_mode /
brightness / colour settings, and leaves the warning and danger states alone.

    get_display_state()  @ vaddr 0x4200a9f6  (file offset 0x4a9f6)
        before:  c.li a0, 0   bytes 01 45
        after:   c.li a0, 1   bytes 05 45
"""
import sys, struct, hashlib

PATCH_OFF = 0x4a9f6      # file offset of the c.li a0, imm we flip
PATCH_OLD = 0x01         # c.li a0, 0  (low byte of 0x4501)
PATCH_NEW = 0x05         # c.li a0, 1  (low byte of 0x4505)

STOCK_SHA = "c12b74cd9541d95c8744d9f8169e84d7865bab40f16be56929bc860df920536f"
OUT_SHA   = "f739aeaf3af8b069e532ffccc25463d42d0176dfb946e8819e342475410560c8"


def esp_image_trailer(d):
    """Return (checksum_offset, hash_offset) for an ESP32 app image."""
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

    if d[PATCH_OFF] != PATCH_OLD:
        print(f"error: byte at 0x{PATCH_OFF:x} is 0x{d[PATCH_OFF]:02x}, expected "
              f"0x{PATCH_OLD:02x}. this is not the expected image.")
        return 1

    d[PATCH_OFF] = PATCH_NEW

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
