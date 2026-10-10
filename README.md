# PyWinAudio

A hardware-style rack for Equalizer APO. Devices are stacked top to bottom, and the
sound passes through them in that order. Every knob writes straight into
Equalizer APO's config, so a change is heard about as soon as the knob stops.

Equalizer APO stays installed as it is and does the actual processing inside the
Windows audio service. This app only writes text files into its config folder.
Nothing needs to be running for the sound to stay processed. Close the app and the
rack keeps playing.

## Devices

- **Preamp**: overall level. **Match** pulls the gain down by the rack's peak boost
  so a full-scale signal cannot clip.
- **Parametric EQ**: up to 20 bands (peak, low/high shelf, low/high cut) on a
  response screen. Drag a point to move its frequency and gain, double-click an
  empty spot to add a band.
- **Graphic EQ**: 15 faders, ±12 dB. A GraphicEQ line imported with more than 31
  points shows as a curve and can be resampled to 15 bands.
- **Delay**: up to 300 ms, on both channels or one.
- **Stereo**: balance, width (0 = mono, 200 % = wide), swap left and right.
- **VST plugin**: any 64-bit VST2 plugin. Its first parameters sit on the front
  panel as knobs, and **Edit** opens the plugin's own editor. Values changed in the
  editor are read back and written to the config while it is open.
- **Custom lines**: lines the rack does not understand (`Device:`, `Eval:` …),
  kept in their original order.

Knobs turn by dragging up and down. Hold Shift for fine steps, double-click to reset.
The mouse wheel always scrolls the rack, so passing over a knob never changes it.

## Linking

The first time, the rack shows **Link**. Linking moves the current `config.txt` aside
to `config-before-pywinaudio.txt`, imports what it can read from it into the rack
(so the sound does not change at that moment), and leaves `config.txt` with a single
`Include: pywinaudio.txt` line. From then on the rack owns `pywinaudio.txt`.

**Settings → Unlink** puts the previous `config.txt` back. **Settings → Devices** opens
Equalizer APO's device selector, which is where outputs are chosen.

## Notes

- The VST2 host is plain `ctypes` (`vsthost.py`). Plugins are loaded into this process
  only to show their editor and read their parameters. Audio never goes through it.
  A plugin is loaded the first time it is touched, not at startup.
- 32-bit plugins cannot load here, and Equalizer APO cannot load them in the 64-bit
  audio service either. VST3 is not supported by Equalizer APO.
- No elevation: Equalizer APO's config folder is writable by Users. Only the device
  selector asks for elevation, because it writes to HKLM.
- Files are written whole and swapped in, so the engine never reads a half-written one.
- Settings and the rack live in `%APPDATA%\PyWinAudio\settings.json`.

## Running

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.pip
.venv\Scripts\pythonw source\main.pyw
```

`source/makeshortcut.py` puts a Start menu link, and `source/makeicon.py` redraws the icon.
