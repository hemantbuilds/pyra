"""
core/audio_devices.py — pick which microphone and which speakers PYRA uses.

WHY
    Both audio streams in main.py were opened without a `device=` argument, so
    they always took whatever the operating system called "default". On a laptop
    with a built-in mic, a webcam mic and a headset that is a coin toss — and on
    Windows the default *moves on its own* the moment you plug a headset in.
    "PYRA can't hear me" almost always means "PYRA is listening to the
    monitor's microphone".

WHY NAMES, NOT INDICES
    sounddevice identifies devices by integer index, and those indices shift
    whenever a device appears or disappears. Storing index 3 means that after
    unplugging a USB interface the saved setting silently points at something
    else. We store the device *name* and resolve it to an index at open time.

WHY THIS IS CACHED
    `sd.query_devices()` talks to the host audio API and can take a few hundred
    milliseconds on a Windows machine with many endpoints. Mark LV learned this
    lesson the expensive way — a 2.1-second `openwakeword` import on the Qt
    thread made the settings drawer look like it was broken. So the list is
    fetched once on a background thread at startup and served from cache.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from typing import Optional

# The label shown for "let the OS decide", and the value stored in config for
# it. Empty string, so an untouched install and a deliberately-default install
# are the same thing — nothing changes for anyone who never opens the picker.
DEFAULT_LABEL = "System default"
DEFAULT_VALUE = ""

_cache: dict[str, list[str]] | None = None
_cache_lock = threading.Lock()

# Which host API each direction settled on, so resolve() opens the same endpoint
# the picker listed. Filled in by _query().
_chosen_api: dict = {"input": None, "output": None}


# ── Why the raw list is unusable, and what is filtered out ───────────────────
#
# `sd.query_devices()` returns one entry per (device × host API), not one per
# device. Measured on a normal Windows machine: 41 entries for what the Windows
# sound settings show as 4 microphones and 4 speakers. The same Realtek
# microphone appears four times — once each under MME, DirectSound, WASAPI and
# WDM-KS — and none of the four is labelled to say which is which.
#
# Handing that to a person is not a choice, it is a quiz. So the list is reduced
# the way the operating system's own settings panel does it:
#
#   1. ONE host API per direction — chosen by measurement, not by reasoning.
#      See the preference note below.
#   2. No pseudo-devices. "Microsoft Sound Mapper", "Primary Sound Driver",
#      ALSA's "default"/"sysdefault"/"dmix" are aliases for "whatever the OS
#      picks" — which is precisely the "System default" entry already at the top
#      of the list. Offering them again as if they were hardware is noise.
#   3. No zero-channel or unnamed entries (WASAPI reports one of each).
#   4. Deduplicated by name.
#
# Nothing is hidden that a person could actually want: the same hardware is
# still there, listed once, under the name their operating system uses for it.

# ── Preference order, which is only a starting point ─────────────────────────
#
# Two earlier versions of this file were wrong in the same way: they decided
# which host API to use by reasoning about it instead of measuring it.
#
#   v1 ranked APIs by how clean their device names were and picked WASAPI.
#      WASAPI in shared mode does not resample — the hardware runs at 48 kHz,
#      this app streams 16 kHz in and 24 kHz out, and every open failed with
#      "Invalid sample rate". The picker looked right and did nothing.
#
#   v2 added a rate check and picked DirectSound, which passes that check on
#      both sides. PortAudio's DirectSound *output* is a silent sink: the
#      stream opens, every write returns success in ~0 ms, and nothing is ever
#      heard. Same failure, one layer deeper.
#
# So this list is a preference, not a promise. Which API actually gets used is
# decided below by _usable() (open it for real) and _transport_works() (does
# audio actually move), per direction. On this platform that lands on
# DirectSound for the microphone and MME for the speakers — a split that no
# amount of reasoning would have produced.
_PREFERRED_APIS = {
    "Windows": ("directsound", "mme", "wasapi"),
    # macOS has only Core Audio, so there is nothing to disambiguate.
    "Darwin":  ("core audio",),
    # PulseAudio/PipeWire present one clean endpoint per device; raw ALSA
    # presents dozens of routing permutations of the same card.
    "Linux":   ("pulse", "pipewire", "jack", "alsa"),
}

# ── "It opens" is not "it works" ─────────────────────────────────────────────
#
# Opening a stream successfully proves nothing. Measured, writing 2.0 s of audio:
#
#     device=None (MME)                    2.02 s   consumed in real time
#     DirectSound, any output device       0.00 s   swallowed instantly
#
# No flag or capability field reports this. The only thing that separates a real
# sink from a fake one is whether it consumes audio at the rate audio is
# consumed at — so that is what gets measured, once per host API per direction,
# on the background thread at startup, using silence.
#
# Each direction is probed **the way main.py actually uses it**. That is not a
# detail: DirectSound input passes a callback stream and fails a blocking read,
# so an earlier version of this probe rejected a microphone that works perfectly
# in the app. Probe the mode you ship, not the mode that is easier to write.
_PROBE_SECONDS = {"output": 0.6, "input": 0.35}

# Cache: {(api_name_or_None, kind): bool}
_probe_results: dict = {}


def _transport_works(idx: int, kind: str, api_key) -> bool:
    """Does this host API actually move audio, or only pretend to?

    Probed once per API per direction and cached. Output writes silence, so the
    probe is inaudible; input reads and discards."""
    if api_key in _probe_results:
        return _probe_results[api_key]

    ok = False
    try:
        import sounddevice as sd
        rate = _RATES.get(kind, 16000)
        secs = _PROBE_SECONDS.get(kind, 0.5)

        # Each direction is probed the way main.py actually uses it. That is not
        # a detail: DirectSound input passes a callback stream and fails a
        # blocking read, so probing the wrong mode rejected a microphone that
        # works perfectly in the app.
        if kind == "output":
            # main.py writes with stream.write() — a real sink is rate-limited
            # by the hardware clock, a fake one swallows the buffer instantly.
            st = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16",
                                    blocksize=1024, device=idx)
            st.start()
            t0 = time.monotonic()
            st.write(bytes(int(rate * secs) * 2))   # silence — inaudible
            elapsed = time.monotonic() - t0
            st.stop(); st.close()
            ok = elapsed > secs * 0.5
            if not ok:
                print(f"[Audio] output: host API reports success but moves no "
                      f"audio ({elapsed*1000:.0f} ms for {secs*1000:.0f} ms) "
                      f"— skipping it")
        else:
            # main.py reads through a callback — count what arrives.
            frames = [0]

            def _cb(indata, n, *_a):
                frames[0] += n

            st = sd.InputStream(samplerate=rate, channels=1, dtype="int16",
                                blocksize=1024, device=idx, callback=_cb)
            st.start()
            time.sleep(secs)
            st.stop(); st.close()
            ok = frames[0] > rate * secs * 0.3
            if not ok:
                print(f"[Audio] input: host API delivered {frames[0]} frames in "
                      f"{secs*1000:.0f} ms — skipping it")
    except Exception as e:
        print(f"[Audio] {kind} transport probe failed: {e}")
        ok = False

    _probe_results[api_key] = ok
    return ok


def _display_name(name: str, devices) -> str:
    """MME truncates device names to 31 characters, so the API that actually
    carries the audio may not be the one that can spell. If another host API
    knows a longer name that starts with this one, show that instead — the user
    reads 'Realtek HD Audio 2nd output (Realtek(R) Audio)' while the stream runs
    on the endpoint called 'Realtek HD Audio 2nd output (Re'."""
    if len(name) < 30:
        return name
    best = name
    for dev in devices:
        other = (dev.get("name") or "").strip()
        if len(other) > len(best) and other.startswith(name):
            best = other
    return best

# The rates the app opens its streams at. Defaults match main.py; main.py calls
# configure() at startup with its own constants so the two can never drift apart
# and silently reintroduce the bug above.
_RATES = {"input": 16000, "output": 24000}


def configure(input_rate: int, output_rate: int) -> None:
    """Tell this module the sample rates the audio streams will use, so the
    picker can rule out devices that cannot be opened at them.

    Drops any cached list: which devices are usable depends on the rate, so a
    list built under the old rates would be stale."""
    global _cache
    _RATES["input"]  = int(input_rate)
    _RATES["output"] = int(output_rate)
    with _cache_lock:
        _cache = None


def _usable(idx: int, kind: str) -> bool:
    """Can this device actually be opened at the rate we need?

    Deliberately opens a real stream rather than asking
    `check_output_settings`, because that function lies: it passed for an MME
    endpoint that then failed to open with "The specified format is not
    supported or cannot be translated" [MME error 32]. Opening and immediately
    closing costs milliseconds and is the only answer that holds."""
    st = None
    try:
        import sounddevice as sd
        rate = _RATES.get(kind, 16000)
        if kind == "input":
            st = sd.InputStream(samplerate=rate, channels=1, dtype="int16",
                                blocksize=1024, device=idx,
                                callback=lambda *_a: None)
        else:
            st = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16",
                                    blocksize=1024, device=idx)
        st.start()
        return True
    except Exception:
        return False
    finally:
        if st is not None:
            try:
                st.stop(); st.close()
            except Exception:
                pass

# Aliases for "the default device" and internal routing endpoints. Matched
# case-insensitively as substrings against the device name.
_PSEUDO_DEVICES = (
    "sound mapper",        # Windows MME
    "primary sound",       # Windows DirectSound ("Primary Sound Capture Driver")
    "sysdefault",          # ALSA
    "default",             # ALSA / PulseAudio alias
    "dmix", "dsnoop",      # ALSA software mixing plugins
    "surround",            # ALSA channel-layout permutations of one card
    "samplerate", "speexrate", "upmix", "vdownmix", "null",
)


def _is_pseudo(name: str) -> bool:
    low = name.lower()
    return any(tok in low for tok in _PSEUDO_DEVICES)


# PipeWire node names, filled by _query(). PortAudio on this machine cannot
# see a Bluetooth speaker, and the USB microphone rejects 16 kHz, so those
# devices are opened with pw-cat instead.
_pw_nodes: dict[str, dict[str, str]] = {"input": {}, "output": {}}
_pw_default: dict[str, str] = {}


def _wpctl_default_ids(text: str) -> dict[str, set[int]]:
    """Object ids marked with * under Sinks and Sources in `wpctl status`."""
    ids: dict[str, set[int]] = {"input": set(), "output": set()}
    section = None
    for line in text.splitlines():
        if "Sinks:" in line:
            section = "output"
            continue
        if "Sources:" in line:
            section = "input"
            continue
        if section and any(tok in line for tok in (
                "Filters:", "Streams:", "Settings", "Devices:")):
            section = None
            continue
        if not section or "*" not in line:
            continue
        match = re.search(r"\*\s+(\d+)\.", line)
        if match:
            ids[section].add(int(match.group(1)))
    return ids


def _load_pipewire() -> dict[str, list[tuple[str, str, bool]]] | None:
    """Bluetooth and other PipeWire endpoints PortAudio does not list.

    -> {'input': [(label, node.name, is_default), ...], 'output': [...]}
    """
    try:
        dump = subprocess.run(
            ["pw-dump"], capture_output=True, text=True, timeout=4,
        )
        if dump.returncode != 0 or not dump.stdout.strip():
            return None
        data = json.loads(dump.stdout)
    except Exception:
        return None

    defaults = {"input": set(), "output": set()}
    try:
        status = subprocess.run(
            ["wpctl", "status"], capture_output=True, text=True, timeout=4,
        )
        defaults = _wpctl_default_ids(status.stdout or "")
    except Exception:
        pass

    found: dict[str, list[tuple[str, str, bool]]] = {"input": [], "output": []}
    for node in data:
        props = ((node.get("info") or {}).get("props") or {})
        media = props.get("media.class")
        kind = {"Audio/Sink": "output", "Audio/Source": "input"}.get(media)
        if not kind:
            continue
        target = str(props.get("node.name") or "").strip()
        label = str(
            props.get("node.description")
            or props.get("node.nick")
            or target
        ).strip()
        if not target or not label or target.endswith(".monitor"):
            continue
        if label in {item[0] for item in found[kind]}:
            label = f"{label} ({target})"
        found[kind].append((
            label, target, node.get("id") in defaults.get(kind, set()),
        ))
    if not found["input"] and not found["output"]:
        return None
    return found


def _merge_pipewire(out: dict[str, list[str]]) -> None:
    """Add PipeWire devices. If PortAudio has nothing usable, they become the list."""
    global _pw_nodes, _pw_default
    catalog = _load_pipewire()
    if not catalog:
        return
    _pw_nodes = {"input": {}, "output": {}}
    _pw_default = {}
    for kind in ("input", "output"):
        for label, target, is_default in catalog[kind]:
            _pw_nodes[kind][label] = target
            if is_default and kind not in _pw_default:
                _pw_default[kind] = target
        if not out[kind] and _pw_nodes[kind]:
            _chosen_api[kind] = "pipewire"
            out[kind] = list(_pw_nodes[kind])
            print(f"[Audio] {kind}: using pipewire ({len(out[kind])} devices)")
        else:
            for label in _pw_nodes[kind]:
                if label not in out[kind]:
                    out[kind].append(label)
    # The Bluetooth speaker also shows up as a microphone and is often listed
    # first, so an empty choice used to record from the speaker. Prefer a
    # wired microphone unless the user picked the Bluetooth one by name.
    chosen = _pw_default.get("input", "")
    if not chosen or chosen.startswith("bluez"):
        for label, target in _pw_nodes["input"].items():
            if target.startswith("bluez"):
                continue
            print(f"[Audio] input: using {label}")
            _pw_default["input"] = target
            break


def pipewire_choice(name: str, kind: str) -> tuple[str, str] | None:
    """(label, pw-cat --target) when this device has to be opened via PipeWire.

    A saved PortAudio device is left alone. An empty choice uses the PipeWire
    default only when PortAudio could not offer anything for this direction.
    """
    list_devices(kind)
    nodes = _pw_nodes.get(kind) or {}
    wanted = (name or "").strip()
    if wanted and wanted != DEFAULT_LABEL and wanted in nodes:
        return wanted, nodes[wanted]
    if (not wanted or wanted == DEFAULT_LABEL) and _chosen_api.get(kind) == "pipewire":
        target = _pw_default.get(kind)
        if target:
            label = next((lbl for lbl, tgt in nodes.items() if tgt == target), target)
            return label, target
        if nodes:
            label, target = next(iter(nodes.items()))
            return label, target
    return None


def pipewire_default(kind: str) -> tuple[str, str] | None:
    """The starred PipeWire sink or source, if PipeWire has one."""
    list_devices(kind)
    nodes = _pw_nodes.get(kind) or {}
    target = _pw_default.get(kind)
    if target:
        label = next((lbl for lbl, tgt in nodes.items() if tgt == target), target)
        return label, target
    if nodes:
        return next(iter(nodes.items()))
    return None


def _query() -> dict[str, list[str]]:
    """Return {'input': [names...], 'output': [names...]}. Never raises.

    Only real, selectable devices — see the note above."""
    out: dict[str, list[str]] = {"input": [], "output": []}
    try:
        import platform
        import sounddevice as sd

        devices = list(sd.query_devices())
        try:
            apis = [a.get("name", "") for a in sd.query_hostapis()]
        except Exception:
            apis = []

        preferred = _PREFERRED_APIS.get(platform.system(), ())

        def _collect(api_filter, kind) -> list[tuple[int, str]]:
            """(index, name) for named, non-pseudo devices on one side that can
            be opened at the rate that side runs at."""
            chan = "max_input_channels" if kind == "input" else "max_output_channels"
            found, seen = [], set()
            for idx, dev in enumerate(devices):
                name = (dev.get("name") or "").strip()
                if not name or _is_pseudo(name) or name in seen:
                    continue
                if dev.get(chan, 0) <= 0:
                    continue
                if api_filter is not None:
                    api = apis[dev["hostapi"]].lower() if dev.get("hostapi", -1) < len(apis) else ""
                    if api_filter not in api:
                        continue
                if not _usable(idx, kind):
                    continue
                seen.add(name)
                found.append((idx, name))
            return found

        # Each direction picks its own host API. They are genuinely different
        # problems — on Windows the microphone works on DirectSound while the
        # speakers only work on MME — and a single global choice cannot be right
        # for both.
        for kind in ("input", "output"):
            for api_filter in list(preferred) + [None]:
                found = _collect(api_filter, kind)
                if not found:
                    continue
                # One probe per API per direction, cached, on this thread.
                if not _transport_works(found[0][0], kind, (api_filter, kind)):
                    continue
                _chosen_api[kind] = api_filter
                out[kind] = [_display_name(n, devices) for _i, n in found]
                break
            if out[kind]:
                print(f"[Audio] {kind}: using "
                      f"{_chosen_api[kind] or 'any host API'} "
                      f"({len(out[kind])} devices)")
        _merge_pipewire(out)
        return out

    except Exception as e:
        print(f"[Audio] Device enumeration failed: {e}")
    return out


def prefetch() -> None:
    """Warm the cache on a background thread. Called once at startup so the
    settings drawer never pays for enumeration on the Qt thread."""
    def _work():
        global _cache
        result = _query()
        with _cache_lock:
            _cache = result
        print(f"[Audio] {len(result['input'])} input / "
              f"{len(result['output'])} output devices found")
    threading.Thread(target=_work, daemon=True, name="audio-devices").start()


def list_devices(kind: str, refresh: bool = False) -> list[str]:
    """Device names for 'input' or 'output'. Falls back to a synchronous query
    if the prefetch has not landed yet — correctness over the cache."""
    global _cache
    with _cache_lock:
        cached = None if refresh else _cache
    if cached is None:
        cached = _query()
        with _cache_lock:
            _cache = cached
    return list(cached.get(kind, []))


def resolve(name: str, kind: str):
    """Turn a saved device name into something sounddevice accepts.

    Returns None for "system default" — which is also what we return when the
    saved device is gone, because a missing headset must degrade to the built-in
    speakers, not to a crash on startup.

    Candidates are walked in the same host-API order the picker used, so a name
    the user chose from the WASAPI list resolves to the WASAPI endpoint. Without
    that ordering a full name would fall through to MME's truncated copy of the
    same device — which happens to work, but means the setting quietly refers to
    a different endpoint than the one on screen."""
    wanted = (name or "").strip()
    if not wanted or wanted == DEFAULT_LABEL:
        return None

    try:
        import platform
        import sounddevice as sd

        devices = list(sd.query_devices())
        try:
            apis = [a.get("name", "") for a in sd.query_hostapis()]
        except Exception:
            apis = []

        want_in  = (kind == "input")
        chan_key = "max_input_channels" if want_in else "max_output_channels"

        def _candidates(api_filter):
            for idx, dev in enumerate(devices):
                if dev.get(chan_key, 0) <= 0:
                    continue
                if api_filter is not None:
                    api = apis[dev["hostapi"]].lower() if dev.get("hostapi", -1) < len(apis) else ""
                    if api_filter not in api:
                        continue
                yield idx, (dev.get("name") or "").strip()

        # The API the picker settled on for this direction comes first — the
        # endpoint that was listed must be the endpoint that gets opened, or the
        # setting means something different from what it says. list_devices()
        # populates it; calling it here is a no-op once the cache is warm.
        list_devices(kind)
        chosen = _chosen_api.get(kind)
        orders = ([chosen] if chosen is not None else []) \
            + [a for a in _PREFERRED_APIS.get(platform.system(), ()) if a != chosen] \
            + [None]

        # A candidate only counts if it can be opened at the rate this side runs
        # at. The prefix match matters because the API that carries the audio is
        # not always the one that can spell: MME truncates names to 31 characters
        # while DirectSound and WASAPI do not, so the name shown in the picker
        # can be longer than the name of the endpoint it actually opens.
        for api_filter in orders:
            partial = None
            for idx, dev_name in _candidates(api_filter):
                if dev_name == wanted:
                    if _usable(idx, kind):
                        return idx
                    continue
                if partial is None and (dev_name.startswith(wanted[:24])
                                        or wanted.startswith(dev_name[:24])):
                    if _usable(idx, kind):
                        partial = idx
            if partial is not None:
                return partial

        print(f"[Audio] Saved {kind} device '{wanted}' cannot be opened at "
              f"{_RATES.get(kind)} Hz on any host API — using system default")
        return None
    except Exception as e:
        print(f"[Audio] resolve({kind}) failed: {e} — using system default")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  The one question automation cannot answer: is it hearing YOU?
# ─────────────────────────────────────────────────────────────────────────────
#
# Everything above decides whether a device can be OPENED and whether it moves
# audio, and it does that with silence so it can run at startup without anyone
# noticing. That is not the same question as "is my microphone picking up my
# voice", and it never will be: a muted mic, a level slider at zero, a headset
# boom pointing at the ceiling and a privacy shutter all pass every automated
# probe in this file and deliver nothing but a flat line.
#
# Only a person can answer that, by speaking. These two functions are what a
# TEST button in the settings panel calls — measure what actually arrives, and
# play something the user can confirm they heard.
#
# This began life as `ses_testi.py`, a loose script in the project root that
# nobody would ever find. It is here because the moment somebody needs it is
# the moment they have opened AUDIO DEVICES wondering why PYRA cannot hear
# them.

# Below this peak, nothing usable arrived; below the second, speech is present
# but so quiet that recognition will struggle. Both are int16 sample values,
# taken from the levels a normal speaking voice produces at arm's length.
_SILENT_PEAK = 100
_QUIET_PEAK = 1500


def _verdict(peak: int) -> dict:
    if peak < _SILENT_PEAK:
        verdict = ("Nothing arrived. The microphone is muted, its level is at "
                   "zero, or this is not the device you are speaking into.")
    elif peak < _QUIET_PEAK:
        verdict = ("Very quiet. Speech recognition will struggle — raise the "
                   "input level in the system sound settings.")
    else:
        verdict = "Working. Your voice is coming through clearly."
    return {"ok": peak >= _QUIET_PEAK, "peak": peak,
            "level": min(1.0, peak / 12000.0), "verdict": verdict}


def _pipewire_measure(target: str, seconds: float, on_level=None) -> dict:
    """Record from a PipeWire source. PipeWire resamples to 16 kHz for us."""
    peak = 0
    proc = None
    try:
        import numpy as np

        rate = _RATES.get("input", 16000)
        proc = subprocess.Popen(
            ["pw-cat", "--target", target, "--record", "--raw",
             "--format", "s16", "--rate", str(rate), "--channels", "1", "-"],
            stdout=subprocess.PIPE,
        )
        deadline = time.monotonic() + seconds
        chunk = rate // 10 * 2
        while time.monotonic() < deadline:
            data = proc.stdout.read(chunk) if proc.stdout else b""
            if not data:
                break
            block = int(np.abs(np.frombuffer(data, dtype="<i2")).max())
            if block > peak:
                peak = block
            if on_level is not None:
                try:
                    on_level(min(1.0, block / 12000.0))
                except Exception:
                    pass
    except Exception as e:
        return {"ok": False, "peak": 0, "level": 0.0,
                "verdict": f"This microphone could not be opened: {e}"}
    finally:
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
    return _verdict(peak)


def measure_input(name: str, seconds: float = 3.0, on_level=None) -> dict:
    """Record from one microphone and report what actually arrived.

    -> {"ok", "peak", "level", "verdict"} — `level` is 0.0-1.0 for a meter,
    `verdict` a short English sentence for the panel. Never raises: a device
    that cannot be opened is a result, not an exception, because the user is
    standing in front of the panel waiting for an answer either way.

    `on_level(0.0-1.0)` is called as the audio arrives, roughly twenty times a
    second, so the caller can move a meter WHILE the user is speaking.

    THE METER IS NOT DECORATION.
        The first version recorded for three seconds and then printed a
        verdict. Reported as "I saw no sign of anything, no level, no
        movement" — which is exactly right: three seconds of a static label
        reading "Speak now" is indistinguishable from a test that has hung.
        A person needs to see the thing respond to their voice to believe it
        is listening, and that is the entire point of the button.
    """
    choice = pipewire_choice(name, "input")
    if choice:
        return _pipewire_measure(choice[1], seconds, on_level)
    idx = resolve(name, "input")
    peak_seen = [0]
    try:
        import numpy as np
        import sounddevice as sd

        rate = _RATES.get("input", 16000)

        def _cb(indata, _frames, _t, _status):
            block = int(np.abs(np.frombuffer(indata, dtype="int16")).max())                 if len(indata) else 0
            if block > peak_seen[0]:
                peak_seen[0] = block
            if on_level is not None:
                try:
                    on_level(min(1.0, block / 12000.0))
                except Exception:
                    pass

        stream = sd.RawInputStream(samplerate=rate, channels=1, dtype="int16",
                                   blocksize=int(rate / 20), device=idx,
                                   callback=_cb)
        with stream:
            time.sleep(max(0.5, float(seconds)))
        peak = peak_seen[0]
    except Exception as e:
        return {"ok": False, "peak": 0, "level": 0.0,
                "verdict": f"This microphone could not be opened: {e}"}

    if peak < _SILENT_PEAK:
        verdict = ("Nothing arrived. The microphone is muted, its level is at "
                   "zero, or this is not the device you are speaking into.")
    elif peak < _QUIET_PEAK:
        verdict = ("Very quiet. Speech recognition will struggle — raise the "
                   "input level in the system sound settings.")
    else:
        verdict = "Working. Your voice is coming through clearly."

    return {"ok": peak >= _QUIET_PEAK, "peak": peak,
            "level": min(1.0, peak / 12000.0), "verdict": verdict}


def _pipewire_tone(target: str, seconds: float) -> dict:
    """Play the test tone through a PipeWire node PortAudio cannot open."""
    try:
        import numpy as np

        rate = _RATES.get("output", 24000)
        t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
        tone = (np.sin(2 * np.pi * 660 * t) * 6000).astype("<i2").tobytes()
        subprocess.run(
            ["pw-cat", "--target", target, "--playback", "--raw",
             "--format", "s16", "--rate", str(rate), "--channels", "1",
             "--latency", "80ms", "-"],
            input=tone, timeout=seconds + 4, check=True,
        )
    except Exception as e:
        return {"ok": False, "verdict": f"This output could not be played: {e}"}
    return {"ok": True, "verdict": "Tone played. Did you hear it?"}


def play_tone(name: str, seconds: float = 0.6) -> dict:
    """Play a short tone through one output so the user can confirm they hear it.

    -> {"ok", "verdict"}. There is no way to check this from software — the
    silent-sink probe above proves audio was CONSUMED, not that a speaker made
    a sound — so the answer comes from the person, and this only makes the
    sound for them to answer about.
    """
    choice = pipewire_choice(name, "output")
    if choice:
        return _pipewire_tone(choice[1], seconds)
    idx = resolve(name, "output")
    try:
        import numpy as np
        import sounddevice as sd

        rate = _RATES.get("output", 24000)
        t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
        # 660 Hz, well inside every speaker's range and unmistakable against
        # room noise. Quiet enough not to startle somebody wearing headphones.
        tone = (np.sin(2 * np.pi * 660 * t) * 6000).astype(np.int16)
        sd.play(tone, samplerate=rate, device=idx)
        sd.wait()
    except Exception as e:
        return {"ok": False, "verdict": f"This output could not be played: {e}"}
    return {"ok": True, "verdict": "Tone played. Did you hear it?"}


# ─────────────────────────────────────────────────────────────────────────────
#  Output volume, so the panel can set it where the device is chosen
# ─────────────────────────────────────────────────────────────────────────────
#
# Choosing "Realtek(R) Audio" in this panel and then finding it far too quiet
# means going to the system sound settings, finding the same endpoint again and
# moving a slider there — reported as exactly that annoyance. The volume
# belongs beside the device it applies to.
#
# These delegate to actions/computer_settings, which already owns the
# per-platform volume plumbing and had a real bug in it (see
# _win_endpoint_volume there). One implementation, not two.

def _endpoint_for(name: str):
    """The Windows volume interface for ONE named output, or None.

    WHY THIS IS NOT JUST THE DEFAULT DEVICE
        The first version set the system's default endpoint, so moving the
        slider in this panel changed the volume of whichever output Windows
        happened to consider default — not the one chosen two lines above it.

        That is wrong in a way that matters to how people actually use this:
        somebody puts the assistant on their speakers and keeps everything else
        in their headphones, and a slider labelled with one device silently
        moving the other is worse than having no slider.

        It also explains a complaint that looked separate. The selected output
        here was sitting at 10% while the default endpoint was at 100% — so the
        assistant was almost inaudible, and the slider "fixed" it by turning up
        something the user could not hear either.

    Matching is by the name Windows itself reports, which is the same string
    sounddevice lists, folded so case and punctuation cannot separate them.
    """
    if _platform_is() != "Windows" or not name:
        return None
    try:
        from pycaw.pycaw import AudioUtilities
        wanted = _fold(name)
        if not wanted:
            return None

        # Collect first, decide after. An earlier version returned the first
        # candidate that matched on a PREFIX, which meant a loosely-similar
        # name could win over the exact one simply by coming first in the
        # enumeration — and the slider then moved a device the user had not
        # chosen. Exact wins, always; the prefix pass exists only because MME
        # truncates long names to 31 characters.
        exact, partial = None, None
        for dev in AudioUtilities.GetAllDevices():
            # ONLY ACTIVE ENDPOINTS, AND THIS IS NOT A TIDINESS FILTER.
            #
            # Windows keeps a record of hardware that is no longer here, and it
            # keeps the SAME FRIENDLY NAME. Measured on this machine, two
            # devices answered to "Hoparlör (Realtek(R) Audio)": one
            # NotPresent sitting at 100%, and the real one, Active, at 10%.
            # Matching by name alone returned whichever came first — so the
            # panel read 100% for a speaker that was actually at 10%, and
            # setting it moved a device that does not exist.
            try:
                if str(getattr(dev, "state", "")) != "AudioDeviceState.Active":
                    continue
            except Exception:
                continue
            try:
                # Reading this property activates a COM interface and raises
                # for devices that are unplugged or disabled — normal, and not
                # worth a line in the log for each one.
                endpoint = dev.EndpointVolume
            except Exception:
                continue
            if endpoint is None:
                continue
            try:
                friendly = _fold(getattr(dev, "FriendlyName", "") or "")
            except Exception:
                continue
            if not friendly:
                continue
            if friendly == wanted:
                exact = endpoint
                break
            if partial is None and (friendly.startswith(wanted[:24])
                                    or wanted.startswith(friendly[:24])):
                partial = endpoint
        return exact or partial
    except Exception as e:
        print(f"[Audio] per-device volume unavailable: {e}")
    return None


def _platform_is() -> str:
    import platform
    return platform.system()


def _fold(text: str) -> str:
    """Same reduction core/appidentity uses for application names — imported
    lazily so this module keeps working if that one is ever absent."""
    try:
        from core.appidentity import fold
        return fold(text)
    except Exception:
        return "".join(c for c in str(text or "").lower() if c.isalnum())


def get_output_volume(name: str = "") -> Optional[int]:
    """Volume 0-100 of ONE output, or of the system default when unnamed.

    None where the platform will not report it — macOS and Linux have no
    per-device volume through this plumbing, so a name there falls back to the
    master level rather than silently answering about the wrong device.
    """
    endpoint = _endpoint_for(name)
    if endpoint is not None:
        try:
            return max(0, min(100, round(
                endpoint.GetMasterVolumeLevelScalar() * 100)))
        except Exception as e:
            print(f"[Audio] could not read '{name}' volume: {e}")
    try:
        from actions.computer_settings import volume_get
        return volume_get()
    except Exception as e:
        print(f"[Audio] could not read the output volume: {e}")
        return None


def set_output_volume(percent: int, name: str = "") -> bool:
    """Set ONE output's volume 0-100. -> did it take.

    Falls back to the system master only when the named device cannot be
    reached, and says so, because silently moving a different device's volume
    is the bug this function exists to fix.
    """
    percent = max(0, min(100, int(percent)))
    endpoint = _endpoint_for(name)
    if endpoint is not None:
        try:
            endpoint.SetMasterVolumeLevelScalar(percent / 100.0, None)
            return True
        except Exception as e:
            print(f"[Audio] could not set '{name}' volume: {e}")
    if name:
        print(f"[Audio] '{name}' has no separate volume control here — "
              f"setting the system level instead.")
    try:
        from actions.computer_settings import volume_set, volume_get
        volume_set(percent)
        now = volume_get()
        return now is None or abs(now - percent) <= 3
    except Exception as e:
        print(f"[Audio] could not set the output volume: {e}")
        return False
