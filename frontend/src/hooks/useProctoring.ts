'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

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

export function useProctoring(videoRef: React.RefObject<HTMLVideoElement>) {
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

  const addEvent = useCallback((type: string, details?: string) => {
    const event: ProctoringEvent = { type, timestamp: Date.now(), details };
    setEvents(prev => [...prev.slice(-99), event]);
  }, []);

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

  // Start/stop monitoring
  const startMonitoring = useCallback(() => {
    setIsMonitoring(true);
    addEvent('monitoring_started', 'Proctoring monitoring started');
  }, [addEvent]);

  const stopMonitoring = useCallback(() => {
    setIsMonitoring(false);
    addEvent('monitoring_stopped', 'Proctoring monitoring stopped');
  }, [addEvent]);

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

// Face detection hook (requires face-api.js)
export function useFaceDetection(videoRef: React.RefObject<HTMLVideoElement>) {
  const [faces, setFaces] = useState<number>(0);
  const [isLooking, setIsLooking] = useState(true);
  const [modelLoaded, setModelLoaded] = useState(false);

  const detectFaces = useCallback(async () => {
    // This would require face-api.js to be loaded
    // For now, we'll implement a placeholder
    if (!videoRef.current || !modelLoaded) return;

    try {
      // Placeholder for face detection
      // In production, use: const detections = await faceapi.detectAllFaces(videoRef.current)
      setFaces(1); // Assume single face
      setIsLooking(true);
    } catch (error) {
      console.error('Face detection error:', error);
    }
  }, [videoRef, modelLoaded]);

  return {
    faces,
    isLooking,
    modelLoaded,
    detectFaces,
  };
}

// Screen text detection hook (requires Tesseract.js)
export function useScreenTextDetection(videoRef: React.RefObject<HTMLVideoElement>) {
  const [suspiciousText, setSuspiciousText] = useState<string[]>([]);
  const [isScanning, setIsScanning] = useState(false);

  const scanScreen = useCallback(async () => {
    if (!videoRef.current || !isScanning) return;

    try {
      // This would require Tesseract.js
      // For now, we'll keep it as a placeholder
      // In production: const { data: { text } } = await Tesseract.recognize(videoElement)
    } catch (error) {
      console.error('OCR error:', error);
    }
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
  };
}

export type { ProctoringEvent, ProctoringStats };
