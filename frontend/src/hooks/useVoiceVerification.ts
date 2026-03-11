'use client';

import { useState, useRef, useEffect, useCallback } from 'react';

interface VoiceVerificationState {
  status: 'idle' | 'ready' | 'recording' | 'playing' | 'verified' | 'failed';
  audioLevel: number;
  recordedBlob: Blob | null;
  error: string | null;
}

const VERIFICATION_PHRASE = "I am ready to start the interview";

export function useVoiceVerification() {
  const [state, setState] = useState<VoiceVerificationState>({
    status: 'idle',
    audioLevel: 0,
    recordedBlob: null,
    error: null,
  });

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const audioElementRef = useRef<HTMLAudioElement | null>(null);

  const startRecording = useCallback(async () => {
    try {
      setState(s => ({ ...s, status: 'recording', error: null, audioLevel: 0 }));

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Set up audio analysis for level monitoring
      audioContextRef.current = new AudioContext();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);

      // Start level monitoring
      const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
      const monitorLevel = () => {
        if (analyserRef.current) {
          analyserRef.current.getByteFrequencyData(dataArray);
          const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
          const level = Math.min(100, Math.round((average / 255) * 100));
          setState(s => ({ ...s, audioLevel: level }));
          animationFrameRef.current = requestAnimationFrame(monitorLevel);
        }
      };
      monitorLevel();

      // Start recording
      mediaRecorderRef.current = new MediaRecorder(stream, { 
        mimeType: 'audio/webm;codecs=opus' 
      });
      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setState(s => ({ ...s, recordedBlob: blob, status: 'ready' }));
        
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
        
        // Stop level monitoring
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
      };

      mediaRecorderRef.current.start(100);

    } catch (err: any) {
      setState(s => ({ 
        ...s, 
        status: 'failed', 
        error: 'Could not access microphone. Please allow microphone access.' 
      }));
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const playRecording = useCallback(() => {
    if (!state.recordedBlob) return;

    setState(s => ({ ...s, status: 'playing' }));

    if (!audioElementRef.current) {
      audioElementRef.current = new Audio();
    }

    audioElementRef.current.src = URL.createObjectURL(state.recordedBlob);
    audioElementRef.current.onended = () => {
      setState(s => ({ ...s, status: 'verified' }));
    };
    audioElementRef.current.play();
  }, [state.recordedBlob]);

  const reset = useCallback(() => {
    if (audioElementRef.current) {
      audioElementRef.current.pause();
      audioElementRef.current.src = '';
    }
    setState({
      status: 'idle',
      audioLevel: 0,
      recordedBlob: null,
      error: null,
    });
  }, []);

  const verifyAndProceed = useCallback(() => {
    // User must have recorded and played back the audio
    if (state.recordedBlob && state.status === 'verified') {
      return true;
    } else {
      setState(s => ({ 
        ...s, 
        error: 'Please record your voice and play it back to verify.' 
      }));
      return false;
    }
  }, [state.recordedBlob, state.status]);

  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
      if (audioElementRef.current) {
        audioElementRef.current.pause();
      }
    };
  }, []);

  return {
    state,
    verificationPhrase: VERIFICATION_PHRASE,
    startRecording,
    stopRecording,
    playRecording,
    reset,
    verifyAndProceed,
  };
}
