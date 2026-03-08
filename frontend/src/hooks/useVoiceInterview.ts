'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { 
  ConnectOptions, 
  Room, 
  RoomEvent, 
  LocalTrack, 
  RemoteTrack,
  LocalVideoTrack,
  LocalAudioTrack,
  RemoteParticipant,
  VideoPresets,
  AudioPresets
} from 'livekit-client';

interface UseVoiceInterviewOptions {
  interviewId: number;
  candidateId: number;
  onQuestionReceived?: (question: string) => void;
  onAnswerTranscribed?: (text: string) => void;
}

export function useVoiceInterview({ 
  interviewId, 
  candidateId,
  onQuestionReceived,
  onAnswerTranscribed 
}: UseVoiceInterviewOptions) {
  const [room, setRoom] = useState<Room | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const localAudioRef = useRef<HTMLAudioElement>(null);
  const agentAudioRef = useRef<HTMLAudioElement>(null);

  const connect = useCallback(async () => {
    try {
      setError(null);
      
      // Get token from backend
      const response = await fetch(`http://localhost:8000/api/v1/voice/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interview_id: interviewId, candidate_id: candidateId })
      });
      
      if (!response.ok) {
        throw new Error('Failed to get interview token');
      }
      
      const { token, url } = await response.json();
      
      // Create room
      const newRoom = new Room({
        adaptiveStream: true,
        dynacast: true,
        videoCaptureDefaults: {
          ...VideoPresets.h720,
          facingMode: 'user'
        },
        audioCaptureDefaults: AudioPresets.music,
      });
      
      // Set up event listeners
      newRoom.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
        if (track.kind === 'audio' && participant.identity === 'agent') {
          if (agentAudioRef.current) {
            track.attach(agentAudioRef.current);
          }
          setIsSpeaking(true);
        }
      });
      
      newRoom.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === 'audio') {
          setIsSpeaking(false);
        }
      });
      
      newRoom.on(RoomEvent.ParticipantConnected, (participant) => {
        console.log('Agent connected:', participant.identity);
        if (participant.identity === 'agent') {
          setIsListening(true);
        }
      });
      
      newRoom.on(RoomEvent.ParticipantDisconnected, (participant) => {
        if (participant.identity === 'agent') {
          setIsListening(false);
        }
      });
      
      // Connect to room
      await newRoom.connect(url, token, {
        autoSubscribe: true,
      } as ConnectOptions);
      
      // Publish local tracks
      const localTracks = await newRoom.localParticipant.enableMicrophoneAndCamera();
      for (const track of localTracks) {
        if (track.kind === 'video' && localVideoRef.current) {
          track.attach(localVideoRef.current);
        }
      }
      
      setRoom(newRoom);
      setIsConnected(true);
      
    } catch (err: any) {
      console.error('Failed to connect:', err);
      setError(err.message || 'Failed to connect to interview');
    }
  }, [interviewId, candidateId]);

  const disconnect = useCallback(async () => {
    if (room) {
      await room.disconnect();
      setRoom(null);
      setIsConnected(false);
      setIsSpeaking(false);
      setIsListening(false);
    }
  }, [room]);

  const startSpeaking = useCallback(async () => {
    if (room) {
      await room.localParticipant.setMicrophoneEnabled(true);
      setIsSpeaking(true);
    }
  }, [room]);

  const stopSpeaking = useCallback(async () => {
    if (room) {
      await room.localParticipant.setMicrophoneEnabled(false);
      setIsSpeaking(false);
    }
  }, [room]);

  useEffect(() => {
    return () => {
      if (room) {
        room.disconnect();
      }
    };
  }, []);

  return {
    room,
    isConnected,
    isSpeaking,
    isListening,
    error,
    localVideoRef,
    agentAudioRef,
    connect,
    disconnect,
    startSpeaking,
    stopSpeaking,
  };
}
