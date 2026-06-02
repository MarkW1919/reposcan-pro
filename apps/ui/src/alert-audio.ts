/*
 * Recovery-alert audio cues.
 *
 * A repo driver's eyes are on the road, so a hotlist match must be audible,
 * not just visual. The "Audible alerts" setting previously described "Play
 * tone on recovery match" but nothing ever played it. This module provides:
 *
 *   - playRecoveryAlertTone(): a short synthesized urgent chirp via the Web
 *     Audio API (no audio asset to ship or fail to load offline).
 *   - speakPlate(): announces the matched plate via speech synthesis so the
 *     driver can register the hit without looking down.
 *
 * Everything is best-effort and guarded: missing APIs, autoplay restrictions,
 * or synthesis errors degrade silently to the visual alert.
 */

let sharedContext: AudioContext | null = null;

type AudioContextCtor = typeof AudioContext;

function getAudioContext(): AudioContext | null {
  if (typeof window === "undefined") {
    return null;
  }
  const Ctor: AudioContextCtor | undefined =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioContextCtor }).webkitAudioContext;
  if (!Ctor) {
    return null;
  }
  if (sharedContext === null) {
    try {
      sharedContext = new Ctor();
    } catch {
      return null;
    }
  }
  return sharedContext;
}

/**
 * Play a short three-note urgent chirp. Safe to call repeatedly; each call
 * schedules its own oscillators so overlapping alerts do not collide.
 */
export function playRecoveryAlertTone(): void {
  const ctx = getAudioContext();
  if (ctx === null) {
    return;
  }
  // Browsers may start the context suspended until a user gesture; resume is
  // a no-op when already running and harmless otherwise.
  void ctx.resume?.().catch(() => undefined);

  const now = ctx.currentTime;
  const notes = [
    { freq: 880, start: 0.0, dur: 0.16 },
    { freq: 1320, start: 0.2, dur: 0.16 },
    { freq: 880, start: 0.4, dur: 0.2 },
  ];

  for (const note of notes) {
    try {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = note.freq;
      // Quick attack, exponential release; keep peak modest so it cuts
      // through cab noise without being painful.
      gain.gain.setValueAtTime(0.0001, now + note.start);
      gain.gain.exponentialRampToValueAtTime(0.16, now + note.start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + note.start + note.dur);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + note.start);
      osc.stop(now + note.start + note.dur + 0.02);
    } catch {
      // Ignore a single failed note; the visual alert still fires.
    }
  }
}

/**
 * Speak the matched plate so the driver can register a hit hands-free.
 * Characters are spaced so plates are read out individually ("A B C 1 2 3")
 * rather than as a garbled word.
 */
export function speakPlate(plate: string): void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return;
  }
  const cleaned = plate.trim();
  if (cleaned.length === 0) {
    return;
  }
  try {
    const spaced = cleaned.split("").join(" ");
    const utterance = new SpeechSynthesisUtterance(`Recovery match. Plate ${spaced}.`);
    utterance.rate = 0.95;
    utterance.volume = 1.0;
    // Cancel any queued speech so a fresh match is not stuck behind a stale one.
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  } catch {
    // Speech is a bonus; ignore failures.
  }
}

/** Stop any in-progress spoken announcement (e.g. when the driver mutes). */
export function stopSpeaking(): void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return;
  }
  try {
    window.speechSynthesis.cancel();
  } catch {
    // ignore
  }
}
