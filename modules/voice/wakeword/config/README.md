# Wakeword Config

This file documents the default configuration for the wakeword module.

## server
- host: API bind address
- port: API bind port

## audio
- device: ALSA device name or index (null = default)
- samplerate: audio sample rate
- channels: audio channels (1 = mono)
- dtype: PCM dtype (int16)
- frame_ms: frame size in ms

## wakeword
- engine: wakeword engine (openwakeword)
- words: list of wakeword phrases
- trigger_on_partial: allow partial results to trigger
- min_confidence: minimum confidence for final results
- cooldown_sec: minimum seconds between triggers

## openwakeword
- model_paths: list or map of models (label -> path)
- threshold: trigger threshold
- smooth_window: moving average window for scores

## actions
- speech_start_url: POST start speech recognition
- speech_stop_url: POST stop speech recognition
- speech_last_url: GET last speech result
- interactions_event_url: POST interaction events
- listen_window_sec: how long to keep speech on after wakeword
- stop_on_final: stop on first final result
- poll_interval_ms: polling interval for speech_last_url
