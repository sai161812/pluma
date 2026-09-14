# Audio visualizer checks

Run from the repository root:

```powershell
dotnet run --project PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj
```

This dependency-free harness compiles the actual production analyzer and motion
helper. It covers silence, noise floor, frequency discrimination, loudness,
determinism, invalid samples, clipping, onset bounds and release at 30/60/120 FPS.

## Windows integration checks (required; not executed in the editing session)

1. Build PLUMA.UI in Debug/x64. Launch the preview and cancel the microphone
   prompt: Windows must not show capture in use.
2. Reopen and click Start: soft speech produces smaller bars than louder speech;
   different vowels/frequencies change the shape, not just the entire radius.
3. Pause: bars settle. Claps must not produce large instantaneous jumps.
4. Deny Windows microphone access or remove the input device: show Unavailable,
   never fall back to simulated audio.
5. Close while capturing: the microphone indicator must turn off. Repeat 20 times.
6. Check at 100%, 125% and 150% display scaling. Record actual motion and check
   no clipping. DPI placement is inherited from the existing host.
7. The production IPC/STT path is not changed: reuse SetAudioSpectrum from the
   backend voice stream later, without running this preview capture alongside it.

Audio is transient. No file writer, upload or transcription engine is used.
The old VoiceOverlayPreviewGenerator remains available as a separate fixture,
but is no longer connected to the default preview window.

Current verification limitation: source review and a JavaScript numerical
cross-check were possible; no Windows/.NET executor was available. Neither this
C# harness nor the WinUI application has been compiled or run in that session.
