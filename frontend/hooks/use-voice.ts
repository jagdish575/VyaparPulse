"use client";

/**
 * Voice input/output using the browser's built-in Web Speech API (no extra services or dependencies).
 * - Speech recognition: Chrome, Edge and Safari (needs HTTPS or localhost + microphone permission).
 * - Speech synthesis: all modern browsers.
 * Recognition uses en-IN, which transcribes Hinglish grocery requests in Roman script.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

const noopSubscribe = () => () => {};

interface RecognitionResult {
  isFinal: boolean;
  [index: number]: { transcript: string };
}
interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const ERROR_MESSAGES: Record<string, string> = {
  "not-allowed": "Microphone access is blocked. Allow it in your browser's address bar and try again.",
  "service-not-allowed": "Microphone access is blocked. Allow it in your browser's address bar and try again.",
  "no-speech": "I didn't catch that. Tap the mic and try again.",
  "audio-capture": "No microphone was found. Check that one is connected.",
  network: "Voice recognition needs an internet connection. Please try again.",
};

interface VoiceInputOptions {
  lang?: string;
  onInterim: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (message: string) => void;
}

export function useVoiceInput(options: VoiceInputOptions) {
  // Browser capability, read without a set-state-in-effect (false on the server, real value on the client).
  const supported = useSyncExternalStore(noopSubscribe, () => recognitionCtor() !== null, () => false);
  const [listening, setListening] = useState(false);
  const recRef = useRef<Recognition | null>(null);
  const optsRef = useRef(options);
  useEffect(() => {
    optsRef.current = options;
  });

  useEffect(() => () => recRef.current?.abort(), []);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor || recRef.current) return;
    const rec = new Ctor();
    rec.lang = optsRef.current.lang ?? "en-IN";
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    let finalText = "";
    let failed = false;

    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i];
        if (result.isFinal) finalText += result[0].transcript;
        else interim += result[0].transcript;
      }
      optsRef.current.onInterim((finalText + interim).trim());
    };
    rec.onerror = (e) => {
      if (e.error === "aborted") return;
      failed = true;
      optsRef.current.onError(ERROR_MESSAGES[e.error] ?? "Voice input stopped unexpectedly. Please try again.");
    };
    rec.onend = () => {
      recRef.current = null;
      setListening(false);
      if (failed) return;
      if (finalText.trim()) optsRef.current.onFinal(finalText.trim());
      else optsRef.current.onError(ERROR_MESSAGES["no-speech"]);
    };

    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch {
      recRef.current = null;
      setListening(false);
    }
  }, []);

  const stop = useCallback(() => recRef.current?.stop(), []);
  const cancel = useCallback(() => recRef.current?.abort(), []);

  return { supported, listening, start, stop, cancel };
}

// ------------------------------------------------------------------ speaking

export function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** Make a chat reply sound natural when read aloud. */
function toSpeech(text: string): string {
  return text
    .replace(/₹\s?([\d,]+(?:\.\d+)?)/g, "$1 rupees")
    .replace(/#(\d+)/g, "number $1")
    .replace(/\s×\s/g, " of ")
    .replace(/\n+/g, ". ")
    .replace(/\s{2,}/g, " ");
}

export function stopSpeaking() {
  if (canSpeak()) window.speechSynthesis.cancel();
}

export function speak(text: string, lang = "en-IN") {
  if (!canSpeak() || !text.trim()) return;
  const synth = window.speechSynthesis;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(toSpeech(text));
  utterance.lang = lang;
  utterance.rate = 1;
  const voice = synth.getVoices().find((v) => v.lang === lang) ?? synth.getVoices().find((v) => v.lang.startsWith("en"));
  if (voice) utterance.voice = voice;
  synth.speak(utterance);
}
