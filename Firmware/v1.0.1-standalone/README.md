# v1.0.1 standalone (breathing without a printer)

Patched build of the official `v1.0.1` firmware that lets you use the RGB
effects (breathing, static, strobing, color cycle) without pairing the
controller to a printer, with a much smoother and slower breathing animation.

Two changes:
1. run the selected effect when no printer is connected (instead of a forced blue strobe).
2. smoother, slower breathing (finer brightness steps).

# 1. Breathing without a printer

## The problem

On stock firmware, if the controller is not connected to a printer, it ignores
whatever effect you pick in the web UI and shows a hard blue on/off strobe. No
combination of settings gets rid of it: turning the RGB on, turning "Follow
Printer Light" off, turning "Warning Light Override" off, even turning off the
config hotspot all leave the strobe running. So if you just want the light on a
shelf or a rack and never intend to bind it to a printer, breathing is
unusable.

## Cause

The RGB task reads a display state from `get_display_state()` in `app_rgb.c`.
That function only returns the "render the selected effect" state while the
printer MQTT link is up (its connection global reads 3). With no printer it
falls through to a default `return 0`, and the task renders state 0 as effect
index 2, which is Strobing with the default color `#0000FF`. That check sits
above the on/off, follow and warning toggles, which is why nothing in the UI can
override it.

## Fix

One code byte. The default `return 0` becomes `return 1`, so a controller with
no printer renders the selected effect instead of the strobe. It goes through
the normal render path, so it still respects the follow / effect / brightness /
color settings, and the warning and danger states are unchanged.

```
get_display_state()  @ vaddr 0x4200a9f6  (file offset 0x4a9f6)
    before:  c.li a0, 0     bytes 01 45     -> no printer => blue strobe
    after:   c.li a0, 1     bytes 05 45     -> no printer => render selected effect
```

# 2. Smoother, slower breathing

## The problem

The breathing effect keeps a phase that bounces between 0 and 60 and steps it by
`direction (+/-1.0) * 3.0 = +/-3.0` every frame, so a whole breath is only about
40 brightness steps. That is visibly choppy, and it gets worse the slower you
set it, because each of those few steps just gets held longer.

## Fix

Drop the two direction constants from `+/-1.0` to `+/-0.2`, so the step becomes
`+/-0.6` and a breath is about 200 steps: roughly 5x finer (smoother) and 5x
longer (slower, so the slow end of the speed slider now goes well below the old
minimum). The phase range (60) and the `/100` brightness maths are untouched, so
brightness and colour are unchanged.

```
C_f8 @ 0x3c0e63f8 (file offset 0x63f8):  -1.0 -> -0.2   (00 00 80 bf -> cd cc 4c be)
C_fc @ 0x3c0e63fc (file offset 0x63fc):  +1.0 -> +0.2   (00 00 80 3f -> cd cc 4c 3e)
```

These two constants are shared with the H2D printer status fade, which gets the
same slower/smoother timing. That is only visible with an H2D printer connected.

---

In total 9 code/data bytes differ from stock (the one state byte plus the two
4-byte constants), plus the recomputed 1-byte image checksum and 32-byte SHA-256
trailer. Everything else is identical. `esptool image-info` reports the rebuilt
image as valid (checksum valid, hash valid).

There is no published source for this firmware, so this is a binary patch
against the official image rather than a source change.

# Build and flashing

## Files

- `panda_rgb_controller_v1.0.1_standalone.bin` - the patched firmware.
- `apply_patch.py` - regenerates the patched image from the official v1.0.1 bin.
  Run it against the stock file and it produces a byte-identical result, so you
  can confirm the only change is the documented one.

```
python3 apply_patch.py ../v1.0.1/panda_rgb_controller_v1.0.1.bin out.bin
```

Hashes (sha256):

```
stock       c12b74cd9541d95c8744d9f8169e84d7865bab40f16be56929bc860df920536f
standalone  f58ffd02fec5f4e6f0f2c05c7d7e9b270622840845bace9acbcba79869d5309f
```

## Flashing

Use the web UI: Settings -> firmware update -> pick the standalone `.bin`, then
let it reboot. Or from a shell:

```
curl -X POST http://<controller-ip>/ota \
  -H "OTA-Type: ota_fw" \
  --data-binary @panda_rgb_controller_v1.0.1_standalone.bin
```

Then reboot the controller (power cycle, or the reset button in the UI). After
it comes back, pick Breathing in the UI and it runs standalone.

## Reverting

Flash the stock `Firmware/v1.0.1/panda_rgb_controller_v1.0.1.bin` the same way.
The patch only touches the RGB task, not the boot or OTA path, so the controller
keeps booting and serving `/ota` normally.
