# v1.0.1 standalone (breathing without a printer)

Patched build of the official `v1.0.1` firmware that lets you use the RGB
effects (breathing, static, strobing, color cycle) without pairing the
controller to a printer.

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

Only 34 bytes of the image differ from stock: the one code byte, the recomputed
1-byte image checksum, and the recomputed 32-byte SHA-256 trailer. Everything
else is identical. `esptool image-info` reports the rebuilt image as valid
(checksum valid, hash valid).

There is no published source for this firmware, so this is a binary patch
against the official image rather than a source change.

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
standalone  f739aeaf3af8b069e532ffccc25463d42d0176dfb946e8819e342475410560c8
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
