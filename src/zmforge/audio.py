r"""Wave files this repository makes rather than finds.

A generated map that wants a sound has two ways to get one: find audio
somebody else made and carry its licence around, or synthesise it. For the
sounds a zombies map actually needs -- a ring, a tone, a beep -- the second
is a dozen lines of arithmetic and carries no licensing question at all, so
that is what this module does.

The format is the one the mod tools' own documentation asks for: 48 kHz,
signed 16-bit PCM. The UGX wiki page on converting sounds says "Check that
Hz is 48000 ... Signed 16-bit PCM", and the tools' single shipped example,
``sound_assets\tst\test_sound.wav``, is a wave file.

**Loops are built to loop.** A looping alias plays the file end to end and
starts again, so any fade baked into the file becomes a pulse once a second
and any partial cycle at the end becomes a click. Every tone here is
therefore a whole number of cycles long and full amplitude throughout; the
fade in and out belong to the alias (``FadeIn`` / ``FadeOut``) and to the
script (``playloopsound( alias, fade )``, ``stoploopsound( 0.5 )``), which
is where the stock flashbang code puts them.
"""

from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass

__all__ = [
    "SAMPLE_RATE",
    "Tone",
    "ringing_tone",
    "write_wav",
]

#: What the tools' documentation asks for, and what every tone here uses.
SAMPLE_RATE = 48_000

#: Full scale for signed 16-bit PCM.
_FULL_SCALE = 32_767


def write_wav(samples, *, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Mono signed 16-bit PCM wave bytes from an iterable of floats in -1..1.

    Values outside the range are clipped rather than wrapped: wrapping turns
    a loud sample into the opposite-sign loudest sample, which is an audible
    crack, and clipping is merely flat.
    """
    frames = bytearray()
    for value in samples:
        clipped = -1.0 if value < -1.0 else (1.0 if value > 1.0 else value)
        frames += int(round(clipped * _FULL_SCALE)).to_bytes(2, "little", signed=True)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


@dataclass(frozen=True, slots=True)
class Tone:
    """A rendered tone: its bytes and the numbers it was actually made at.

    ``frequency_hz`` is the frequency after rounding to a whole number of
    cycles in the loop, not the one that was asked for, because that is the
    frequency the file holds. The difference is a fraction of a hertz and
    nobody hears it; recording the real one means a later measurement of the
    file agrees with what this says.
    """

    wav: bytes
    frequency_hz: float
    seconds: float
    sample_rate: int
    frames: int

    @property
    def description(self) -> str:
        return (
            f"{self.frequency_hz:.1f} Hz sine, {self.seconds:g} s seamless loop, "
            f"{self.sample_rate} Hz 16-bit mono PCM, synthesised"
        )


def _whole_cycles(frequency_hz: float, seconds: float) -> float:
    """The nearest frequency with a whole number of cycles in *seconds*.

    A loop that ends mid-cycle jumps from wherever the waveform got to back
    to zero, and that step is a click on every repeat.
    """
    cycles = max(1, round(frequency_hz * seconds))
    return cycles / seconds


def ringing_tone(
    *,
    frequency_hz: float = 4_500.0,
    seconds: float = 2.0,
    amplitude: float = 0.35,
    beat_hz: float = 0.5,
    beat_depth: float = 0.12,
    sample_rate: int = SAMPLE_RATE,
) -> Tone:
    """The after-a-blast ring: a high sine that loops without a seam.

    4.5 kHz because that is where the whine of acoustic trauma sits for most
    people; the octave-and-a-fifth partial and the slow beat are there so it
    reads as an ear ringing rather than as a test tone. Both the carrier and
    the beat are rounded to a whole number of cycles per loop, so the last
    sample runs into the first with no step.

    ``amplitude`` is deliberately well under full scale. This plays under a
    concussion effect and over whatever else the fight is doing, and a tone
    at full scale in a mix is not "loud", it is distortion.

    Nothing about how it *reads in play* is verified here. This function
    makes a file; whether six seconds of it is a good joke or an annoyance
    is a question for somebody wearing headphones.
    """
    if not 0.0 < amplitude <= 1.0:
        raise ValueError("amplitude is a fraction of full scale, 0 to 1")
    if seconds <= 0.0:
        raise ValueError("a loop with no length is not a loop")

    carrier = _whole_cycles(frequency_hz, seconds)
    partial = _whole_cycles(frequency_hz * 1.5, seconds)
    beat = _whole_cycles(beat_hz, seconds) if beat_hz > 0.0 else 0.0
    frames = int(round(seconds * sample_rate))

    def samples():
        for index in range(frames):
            t = index / sample_rate
            wobble = (
                1.0 - beat_depth + beat_depth * (0.5 + 0.5 * math.cos(2 * math.pi * beat * t))
                if beat
                else 1.0
            )
            value = math.sin(2 * math.pi * carrier * t)
            value += 0.18 * math.sin(2 * math.pi * partial * t)
            yield amplitude * wobble * value / 1.18

    return Tone(
        wav=write_wav(samples(), sample_rate=sample_rate),
        frequency_hz=carrier,
        seconds=frames / sample_rate,
        sample_rate=sample_rate,
        frames=frames,
    )
