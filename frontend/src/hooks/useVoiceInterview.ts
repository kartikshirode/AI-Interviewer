'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

// Type declarations for Web Speech API
interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  length: number;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
  message: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognitionInstance;
    webkitSpeechRecognition: new () => SpeechRecognitionInstance;
  }
}

export function useVoiceInterview() {
  // ── Real-time transcript state (Web Speech API) ──
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [combinedTranscript, setCombinedTranscript] = useState('');
  const [lastSpeechAt, setLastSpeechAt] = useState<number | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Background audio recording state (MediaRecorder) ──
  const [isRecording, setIsRecording] = useState(false);

  // ── Refs ──
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const finalTranscriptRef = useRef('');
  const shouldRestartRef = useRef(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioStreamRef = useRef<MediaStream | null>(null);

  // ── Cleanup on unmount ──
  useEffect(() => {
    return () => {
      shouldRestartRef.current = false;
      recognitionRef.current?.stop();
      recognitionRef.current = null;
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.stop();
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach(t => t.stop());
        audioStreamRef.current = null;
      }
      recorderRef.current = null;
      audioChunksRef.current = [];
      if (typeof window !== 'undefined') {
        window.speechSynthesis?.cancel();
      }
    };
  }, []);

  // ────────────────────────────────────────────────
  //  TEXT-TO-SPEECH: AI reads the question aloud
  // ────────────────────────────────────────────────
  const speakQuestion = useCallback((text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (typeof window === 'undefined') { resolve(); return; }

      window.speechSynthesis.cancel();

      const speak = () => {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.95;
        utterance.pitch = 1;
        utterance.volume = 1;
        utterance.lang = 'en-US';

        const voices = window.speechSynthesis.getVoices();
        const preferred = voices.find(v => v.lang.startsWith('en') && v.name.includes('Google'))
          || voices.find(v => v.lang.startsWith('en'));
        if (preferred) utterance.voice = preferred;

        utterance.onstart = () => setIsSpeaking(true);
        utterance.onend = () => { setIsSpeaking(false); resolve(); };
        utterance.onerror = () => { setIsSpeaking(false); resolve(); };

        window.speechSynthesis.speak(utterance);
      };

      if (window.speechSynthesis.getVoices().length > 0) {
        speak();
      } else {
        window.speechSynthesis.onvoiceschanged = () => speak();
        setTimeout(speak, 500);
      }
    });
  }, []);

  // ────────────────────────────────────────────────
  //  REAL-TIME SPEECH RECOGNITION (Web Speech API)
  // ────────────────────────────────────────────────
  const startListening = useCallback(() => {
    if (typeof window === 'undefined') return;

    setError(null);

    const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionClass) {
      setError('Speech recognition not supported. Please use Chrome or Edge.');
      return;
    }

    const recognition = new SpeechRecognitionClass();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = '';
      let final = finalTranscriptRef.current;

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript + ' ';
          finalTranscriptRef.current = final;
        } else {
          interim += result[0].transcript;
        }
      }

      const normalizedFinal = final.trim();
      const normalizedInterim = interim.trim();
      const merged = [normalizedFinal, normalizedInterim].filter(Boolean).join(' ').trim();

      setTranscript(normalizedFinal);
      setInterimTranscript(normalizedInterim);
      setCombinedTranscript(merged);

      if (merged.length > 0) {
        setLastSpeechAt(Date.now());
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setError(`Speech recognition error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      if (shouldRestartRef.current && recognitionRef.current === recognition) {
        try {
          recognition.start();
        } catch {
          setIsListening(false);
          shouldRestartRef.current = false;
        }
      } else {
        setIsListening(false);
      }
    };

    recognitionRef.current = recognition;
    shouldRestartRef.current = true;
    recognition.start();
  }, []);

  const stopListening = useCallback(() => {
    shouldRestartRef.current = false;
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
      setIsListening(false);
      setInterimTranscript('');
      setCombinedTranscript(finalTranscriptRef.current.trim());
    }
  }, []);

  // ────────────────────────────────────────────────
  //  BACKGROUND AUDIO RECORDING (MediaRecorder API)
  // ────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;
      audioChunksRef.current = [];

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';

      const recorder = new MediaRecorder(stream, { mimeType });

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        // Stream tracks are stopped in stopRecording
      };

      recorderRef.current = recorder;
      recorder.start(1000); // collect chunks every second
      setIsRecording(true);
    } catch (err) {
      console.error('Failed to start audio recording:', err);
    }
  }, []);

  const stopRecording = useCallback((): Blob | null => {
    let blob: Blob | null = null;

    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    }

    if (audioChunksRef.current.length > 0) {
      blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
    }

    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach(t => t.stop());
      audioStreamRef.current = null;
    }

    recorderRef.current = null;
    audioChunksRef.current = [];
    setIsRecording(false);

    return blob;
  }, []);

  // ────────────────────────────────────────────────
  //  COMBINED START / STOP  (recognition + recording)
  // ────────────────────────────────────────────────
  const startAnswer = useCallback(async () => {
    await startRecording();
    startListening();
  }, [startRecording, startListening]);

  const stopAnswer = useCallback((): Blob | null => {
    stopListening();
    return stopRecording();
  }, [stopListening, stopRecording]);

  // ────────────────────────────────────────────────
  //  HELPERS
  // ────────────────────────────────────────────────
  const stopSpeaking = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript('');
    setInterimTranscript('');
    setCombinedTranscript('');
    setLastSpeechAt(null);
    finalTranscriptRef.current = '';
  }, []);

  return {
    // Real-time transcript
    transcript,
    interimTranscript,
    combinedTranscript,
    lastSpeechAt,
    isListening,
    isSpeaking,
    isRecording,
    error,
    // TTS
    speakQuestion,
    // Recognition
    startListening,
    stopListening,
    // Recording
    startRecording,
    stopRecording,
    // Combined
    startAnswer,
    stopAnswer,
    // Helpers
    stopSpeaking,
    resetTranscript,
  };
}
