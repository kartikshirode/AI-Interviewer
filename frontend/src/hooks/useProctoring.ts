'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/services/api';

const FLUSH_BATCH_SIZE = 10;
const FLUSH_INTERVAL_MS = 30_000;

interface ProctoringEvent {
  type: string;
  timestamp: number;
  details?: string;
}

interface ProctoringStats {
  tabSwitchCount: number;
  clipboardCopyCount: number;
  clipboardPasteCount: number;
  faceAwayCount: number;
  multipleFaceCount: number;
  suspiciousTextCount: number;
}

const SUSPICIOUS_KEYWORDS = [
  'google', 'chatgpt', 'gpt', 'stackoverflow', 'github', 'copilot',
  'bing', 'wikipedia', 'quora', 'reddit', 'youtube', 'course', 'tutorial',
  'answer', 'solution', 'cheat', 'exam', 'test'
];

export function useProctoring(videoRef: React.RefObject<HTMLVideoElement | null>) {
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [stats, setStats] = useState<ProctoringStats>({
    tabSwitchCount: 0,
    clipboardCopyCount: 0,
    clipboardPasteCount: 0,
    faceAwayCount: 0,
    multipleFaceCount: 0,
    suspiciousTextCount: 0,
  });
  const [events, setEvents] = useState<ProctoringEvent[]>([]);
  const [riskLevel, setRiskLevel] = useState<'low' | 'medium' | 'high'>('low');
  
  const tabSwitchCountRef = useRef(0);
  const clipboardCopyRef = useRef(0);
  const clipboardPasteRef = useRef(0);
  const faceAwayRef = useRef(0);
  const multipleFaceRef = useRef(0);
  const suspiciousTextRef = useRef(0);

  // Server-bound batch buffer. Cleared on successful flush; drained on
  // unmount/stopMonitoring. Lifecycle events (`monitoring_started`/...) are
  // dropped server-side, so we don't bother stripping them here.
  const candidateIdRef = useRef<number | null>(null);
  const pendingRef = useRef<ProctoringEvent[]>([]);
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const flushPending = useCallback(async () => {
    const cid = candidateIdRef.current;
    if (cid == null) return;
    if (pendingRef.current.length === 0) return;
    const batch = pendingRef.current;
    pendingRef.current = [];
    try {
      await api.submitProctoringEvents(
        cid,
        batch.map((e) => ({
          event_type: e.type,
          timestamp: e.timestamp,
          details: e.details ? { note: e.details } : null,
        })),
      );
    } catch (err) {
      console.warn('[proctoring] flush failed; re-queueing', err);
      // Push back onto the front so the next flush retries.
      pendingRef.current = [...batch, ...pendingRef.current];
    }
  }, []);

  const addEvent = useCallback((type: string, details?: string) => {
    const event: ProctoringEvent = { type, timestamp: Date.now(), details };
    setEvents(prev => [...prev.slice(-99), event]);
    pendingRef.current.push(event);
    if (pendingRef.current.length >= FLUSH_BATCH_SIZE) {
      void flushPending();
    }
  }, [flushPending]);

  const calculateRiskLevel = useCallback(() => {
    const score = 
      tabSwitchCountRef.current * 10 +
      clipboardCopyRef.current * 5 +
      clipboardPasteRef.current * 10 +
      faceAwayRef.current * 5 +
      multipleFaceRef.current * 20 +
      suspiciousTextRef.current * 15;

    if (score >= 60) {
      setRiskLevel('high');
    } else if (score >= 30) {
      setRiskLevel('medium');
    } else {
      setRiskLevel('low');
    }
  }, []);

  const updateStats = useCallback(() => {
    setStats({
      tabSwitchCount: tabSwitchCountRef.current,
      clipboardCopyCount: clipboardCopyRef.current,
      clipboardPasteCount: clipboardPasteRef.current,
      faceAwayCount: faceAwayRef.current,
      multipleFaceCount: multipleFaceRef.current,
      suspiciousTextCount: suspiciousTextRef.current,
    });
    calculateRiskLevel();
  }, [calculateRiskLevel]);

  // Tab switching detection
  useEffect(() => {
    if (!isMonitoring) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        tabSwitchCountRef.current += 1;
        addEvent('tab_switch', 'User switched to another tab');
        updateStats();
      }
    };

    const handleBlur = () => {
      tabSwitchCountRef.current += 1;
      addEvent('window_blur', 'User left the interview window');
      updateStats();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleBlur);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleBlur);
    };
  }, [isMonitoring, addEvent, updateStats]);

  // Clipboard monitoring
  useEffect(() => {
    if (!isMonitoring) return;

    const handleCopy = (e: ClipboardEvent) => {
      clipboardCopyRef.current += 1;
      addEvent('clipboard_copy', 'User copied text');
      updateStats();
    };

    const handlePaste = (e: ClipboardEvent) => {
      clipboardPasteRef.current += 1;
      addEvent('clipboard_paste', 'User pasted text');
      updateStats();
    };

    document.addEventListener('copy', handleCopy);
    document.addEventListener('paste', handlePaste);

    return () => {
      document.removeEventListener('copy', handleCopy);
      document.removeEventListener('paste', handlePaste);
    };
  }, [isMonitoring, addEvent, updateStats]);

  // Keyboard shortcuts detection (Ctrl+C, Ctrl+V, etc.)
  useEffect(() => {
    if (!isMonitoring) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'c') {
        clipboardCopyRef.current += 1;
        addEvent('keyboard_copy', 'User used Ctrl+C');
        updateStats();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'v') {
        clipboardPasteRef.current += 1;
        addEvent('keyboard_paste', 'User used Ctrl+V');
        updateStats();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 't') {
        tabSwitchCountRef.current += 1;
        addEvent('new_tab', 'User opened new tab');
        updateStats();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isMonitoring, addEvent, updateStats]);

  // Start/stop monitoring. `candidateId` is required so events can be
  // POSTed to the right row server-side.
  const startMonitoring = useCallback((candidateId: number) => {
    candidateIdRef.current = candidateId;
    setIsMonitoring(true);
    addEvent('monitoring_started', 'Proctoring monitoring started');
    if (flushTimerRef.current == null) {
      flushTimerRef.current = setInterval(() => {
        void flushPending();
      }, FLUSH_INTERVAL_MS);
    }
  }, [addEvent, flushPending]);

  const stopMonitoring = useCallback(() => {
    setIsMonitoring(false);
    addEvent('monitoring_stopped', 'Proctoring monitoring stopped');
    if (flushTimerRef.current != null) {
      clearInterval(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    // Drain whatever's left.
    void flushPending();
  }, [addEvent, flushPending]);

  // Drain on unmount as a last-chance flush. Synchronous fetch via
  // `navigator.sendBeacon` would be safer for unloads, but we don't have a
  // beacon-friendly endpoint yet.
  useEffect(() => {
    return () => {
      if (flushTimerRef.current != null) {
        clearInterval(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      void flushPending();
    };
  }, [flushPending]);

  // Get proctoring report
  const getReport = useCallback(() => {
    return {
      events,
      stats,
      riskLevel,
      totalScore: 
        stats.tabSwitchCount * 10 +
        stats.clipboardCopyCount * 5 +
        stats.clipboardPasteCount * 10 +
        stats.faceAwayCount * 5 +
        stats.multipleFaceCount * 20 +
        stats.suspiciousTextCount * 15,
    };
  }, [events, stats, riskLevel]);

  return {
    isMonitoring,
    stats,
    events,
    riskLevel,
    startMonitoring,
    stopMonitoring,
    getReport,
  };
}

// =====================================================================
// STUB: useFaceDetection
// =====================================================================
// TODO(proctoring): wire up real face detection (e.g. face-api.js or
// MediaPipe FaceDetector). Until then, this hook returns placeholder
// values and is NOT a real source of proctoring signal. Do not display
// these numbers as if they reflect what the camera saw.
export function useFaceDetection(videoRef: React.RefObject<HTMLVideoElement>) {
  const [faces, setFaces] = useState<number>(0);
  const [isLooking, setIsLooking] = useState(true);
  const [modelLoaded, setModelLoaded] = useState(false);

  // Warn once per mount so it shows up in dev tools instead of silently
  // pretending to work.
  useEffect(() => {
    console.warn(
      '[proctoring] useFaceDetection is a stub — `faces` and `isLooking` are placeholders, not actual detections.',
    );
  }, []);

  const detectFaces = useCallback(async () => {
    if (!videoRef.current || !modelLoaded) return;
    // STUB: not a real detection.
    setFaces(1);
    setIsLooking(true);
  }, [videoRef, modelLoaded]);

  return {
    faces,
    isLooking,
    modelLoaded,
    detectFaces,
    isStub: true as const,
  };
}

// =====================================================================
// STUB: useScreenTextDetection
// =====================================================================
// TODO(proctoring): integrate Tesseract.js / a real OCR pass over the
// shared screen frame. Until then, `suspiciousText` will only contain
// matches from `checkForSuspiciousText` calls the caller makes manually.
export function useScreenTextDetection(videoRef: React.RefObject<HTMLVideoElement>) {
  const [suspiciousText, setSuspiciousText] = useState<string[]>([]);
  const [isScanning, setIsScanning] = useState(false);

  useEffect(() => {
    console.warn(
      '[proctoring] useScreenTextDetection is a stub — no OCR is actually performed.',
    );
  }, []);

  const scanScreen = useCallback(async () => {
    if (!videoRef.current || !isScanning) return;
    // STUB: no OCR is performed. See TODO above.
  }, [videoRef, isScanning]);

  const checkForSuspiciousText = useCallback((text: string) => {
    const lowerText = text.toLowerCase();
    const found = SUSPICIOUS_KEYWORDS.filter(keyword => lowerText.includes(keyword));
    if (found.length > 0) {
      setSuspiciousText(prev => [...prev, ...found]);
    }
  }, []);

  return {
    suspiciousText,
    isScanning,
    setIsScanning,
    scanScreen,
    checkForSuspiciousText,
    isStub: true as const,
  };
}

export type { ProctoringEvent, ProctoringStats };
