# Service Resilience System Specification

## 1. Overview

The **Service Resilience System** ensures the `Mutter` application remains operational ("seamless operation") despite infrastructure failures (e.g., audio device disconnects, API outages) or non-critical component failures (LLM errors).

**Goal**: Zero intervention required for recovery from common faults.

## 2. Architecture Changes

### A. ServiceManager (Enhanced)

The `ServiceManager` (`src/application/service_manager.py`) evolves from a simple bootstrapper to an active **Health Monitor & Recovery Supervisor**.

**Responsibilities Added:**
1.  **Active Monitoring**: Periodically check health of critical services.
2.  **Reactive Recovery**: Listen for failure signals and trigger specific recovery workflows.
3.  **Dependency Hot-Swapping**: Re-initialize and inject new service instances into consumers (e.g., giving `RecordingService` a new `AudioRecorder`).

**New Methods:**
- `start_monitoring()`: Starts a `QTimer` (e.g., every 30s) to run `check_health()`.
- `check_health()`: Polls `AudioRecorder` and `Transcriber`.
- `recover_audio_service(reason=None)`:
    - Attempts to re-initialize `AudioRecorder`.
    - If specific device is gone, falls back to system default.
    - Injects new recorder into `RecordingService`.
- `recover_transcription_service()`:
    - If GPU fails, falls back to CPU.
    - Re-initializes `Transcriber`.

### B. Service Interfaces (Health Protocol)

Infrastructure services must implement a "Health Protocol" (implicit or explicit):

```python
def is_healthy(self) -> bool:
    """Returns True if service is operational."""
    pass

def get_status(self) -> dict:
    """Returns diagnostic info (e.g., device name, model loaded)."""
    pass
```

### C. RecordingService (Refactored)

The `RecordingService` (`src/infrastructure/recording/recording_service.py`) must support **Hot-Swapping** of its dependencies.

**Changes:**
- Add `set_audio_recorder(recorder)`: Allows replacing the recorder instance at runtime.
- Add `set_transcriber(transcriber)`: Allows replacing the transcriber instance.
- **Error Categorization**: When `recording_failed` is emitted, distinguish between:
    - `InfrastructureError` (Device lost -> Trigger Recovery)
    - `ProcessError` (Transcription failed -> Ignore/Retry)
    - `LogicError` (Bug -> Log)

### D. AppBootstrap (Integration)

**Changes:**
- **Soft Failures**: Remove global exit on initialization error (where possible).
- **Recovery UI**: If critical services fail and cannot recover, show a "Repair" dialog instead of crashing.

---

## 3. Implementation Plan

### Phase 1: Infrastructure Health Checks

1.  **AudioRecorder**: Implement `is_healthy()`.
    - Check if `self.device` (index or name) is still present in `sounddevice.query_devices()`.
2.  **Transcriber**: Implement `is_healthy()`.
    - Check if `self.model` is loaded.
    - Wrap inference in a safety block that detects CUDA errors.

### Phase 2: RecordingService Hot-Swap

1.  Add `update_dependencies(audio_recorder=None, transcriber=None)` to `RecordingService`.
2.  Ensure `RecordingService` uses the *current* instance reference, not a stale one.

### Phase 3: ServiceManager Recovery Logic

1.  Implement `_health_check_timer`.
2.  Implement `_handle_recording_failure(error_msg)`.
    - Parse error. If "Device not found" or "PortAudio" error:
        - Log warning.
        - Call `recover_audio_service()`.
        - Notify User via Tray: "Audio device lost. Switched to default."

### Phase 4: Fault Tolerance (LLM)

1.  In `RecordingService._process_text_with_llm`, wrap strictly.
2.  If LLM fails, return original text and **do not** emit failure signal that stops the flow.
3.  Log LLM failure as warning only.

## 4. Detailed Design: Recovery Workflows

### Scenario 1: Microphone Unplugged
1.  User unplug mic.
2.  User presses Record.
3.  `AudioRecorder.start_recording` raises exception (PortAudio error).
4.  `RecordingService` catches exception.
5.  `RecordingService` emits `recording_failed("Audio device error...")`.
6.  `ServiceManager` (connected to signal) detects audio error.
7.  `ServiceManager` calls `recover_audio_service()`.
    - Scans devices.
    - Initializes new `AudioRecorder` with default device.
    - Calls `recording_service.set_audio_recorder(new_recorder)`.
8.  `ServiceManager` shows Toast: "Microphone disconnected. Switched to Default."
9.  (Optional) Auto-retry recording.

### Scenario 2: GPU Driver Crash (Transcription)
1.  `Transcriber` fails with CUDA error.
2.  `RecordingService` catches exception.
3.  `ServiceManager` detects transcription error.
4.  `ServiceManager` calls `recover_transcription_service()`.
    - Re-inits `Transcriber` with `device="cpu"`.
    - Updates `RecordingService`.
5.  Next recording works on CPU.
