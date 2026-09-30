"""Cross-platform process memory sampling for leak diagnostics.

The memory watchdog originally relied on the ``resource`` module, which does
not exist on Windows — so the one platform where the app has been seen to
balloon produced no telemetry at all. This module reads the *current* and
*peak* resident set size on Windows, macOS and Linux using only the standard
library (no psutil dependency), so the watchdog works in every build.
"""

import ctypes
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_MB = 1024 * 1024


@dataclass(frozen=True)
class MemorySample:
    """Process memory in megabytes."""
    rss_mb: float           # Current resident set / working set
    peak_rss_mb: float      # High-water mark of the resident set
    commit_mb: Optional[float] = None     # Windows only: private bytes (Task Manager "Memory")
    footprint_mb: Optional[float] = None  # macOS only: phys_footprint (Activity Monitor "Memory")

    def describe(self) -> str:
        text = f"rss={self.rss_mb:.1f}MB peak={self.peak_rss_mb:.1f}MB"
        if self.commit_mb is not None:
            text += f" commit={self.commit_mb:.1f}MB"
        if self.footprint_mb is not None:
            text += f" footprint={self.footprint_mb:.1f}MB"
        return text

    @property
    def headline_mb(self) -> float:
        """The number the OS's own task manager would show for this process.

        On macOS that is the physical footprint, which includes pages the
        compressor has taken out of the resident set — a leak of cold pages
        grows this while RSS stays flat. On Windows it is the commit charge.
        """
        if self.footprint_mb is not None:
            return self.footprint_mb
        if self.commit_mb is not None:
            return self.commit_mb
        return self.rss_mb


def region_summary(timeout: float = 60.0) -> str:
    """Per-region memory breakdown of this process, as one line (macOS only).

    Uses the system `footprint` tool, which reports dirty memory by region
    type (MALLOC_LARGE, MALLOC_SMALL, IOKit, CoreAudio, stack, ...). This is
    the fastest way to tell a numpy/ctranslate2 leak from a driver or GPU
    one. Returns "" where unsupported or if the tool fails.
    """
    if sys.platform != "darwin":
        return ""
    import subprocess
    try:
        out = subprocess.run(
            ["/usr/bin/footprint", "-p", str(os.getpid())],
            capture_output=True, text=True, timeout=timeout,
        ).stdout
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"footprint tool failed: {e}")
        return ""
    rows = []
    for line in out.splitlines():
        parts = line.split()
        # Table rows look like:
        #   "<dirty> <unit> <clean> <unit> <reclaimable> <unit> <regions> <category...>"
        if len(parts) >= 8 and parts[1] in ("B", "KB", "MB", "GB") and parts[6].isdigit():
            dirty, unit, category = parts[0], parts[1], " ".join(parts[7:])
            if unit in ("B", "KB") or category == "TOTAL":
                continue
            rows.append(f"{category}={dirty}{unit}")
        if len(rows) >= 8:
            break
    return ", ".join(rows)


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
if sys.platform == "win32":
    from ctypes import wintypes

    class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.GetCurrentProcess.argtypes = []

    # K32GetProcessMemoryInfo lives in kernel32 on Vista+; psapi.dll forwards to it.
    try:
        _GetProcessMemoryInfo = _kernel32.K32GetProcessMemoryInfo
    except AttributeError:
        _GetProcessMemoryInfo = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    _GetProcessMemoryInfo.restype = wintypes.BOOL
    _GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_PROCESS_MEMORY_COUNTERS_EX),
        wintypes.DWORD,
    ]

    def sample() -> Optional[MemorySample]:
        counters = _PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        if not _GetProcessMemoryInfo(_kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            logger.debug(f"GetProcessMemoryInfo failed: {ctypes.get_last_error()}")
            return None
        return MemorySample(
            rss_mb=counters.WorkingSetSize / _MB,
            peak_rss_mb=counters.PeakWorkingSetSize / _MB,
            commit_mb=counters.PrivateUsage / _MB,
        )

# --------------------------------------------------------------------------
# macOS
# --------------------------------------------------------------------------
elif sys.platform == "darwin":
    import resource

    class _ProcTaskInfo(ctypes.Structure):
        # struct proc_taskinfo from <sys/proc_info.h>
        _fields_ = [
            ("pti_virtual_size", ctypes.c_uint64),
            ("pti_resident_size", ctypes.c_uint64),
            ("pti_total_user", ctypes.c_uint64),
            ("pti_total_system", ctypes.c_uint64),
            ("pti_threads_user", ctypes.c_uint64),
            ("pti_threads_system", ctypes.c_uint64),
            ("pti_policy", ctypes.c_int32),
            ("pti_faults", ctypes.c_int32),
            ("pti_pageins", ctypes.c_int32),
            ("pti_cow_faults", ctypes.c_int32),
            ("pti_messages_sent", ctypes.c_int32),
            ("pti_messages_received", ctypes.c_int32),
            ("pti_syscalls_mach", ctypes.c_int32),
            ("pti_syscalls_unix", ctypes.c_int32),
            ("pti_csw", ctypes.c_int32),
            ("pti_threadnum", ctypes.c_int32),
            ("pti_numrunning", ctypes.c_int32),
            ("pti_priority", ctypes.c_int32),
        ]

    class _RusageInfoV0(ctypes.Structure):
        # struct rusage_info_v0 from <sys/resource.h>; ri_phys_footprint is
        # the "Memory" column in Activity Monitor.
        _fields_ = [
            ("ri_uuid", ctypes.c_uint8 * 16),
            ("ri_user_time", ctypes.c_uint64),
            ("ri_system_time", ctypes.c_uint64),
            ("ri_pkg_idle_wkups", ctypes.c_uint64),
            ("ri_interrupt_wkups", ctypes.c_uint64),
            ("ri_pageins", ctypes.c_uint64),
            ("ri_wired_size", ctypes.c_uint64),
            ("ri_resident_size", ctypes.c_uint64),
            ("ri_phys_footprint", ctypes.c_uint64),
            ("ri_proc_start_abstime", ctypes.c_uint64),
            ("ri_proc_exit_abstime", ctypes.c_uint64),
        ]

    _PROC_PIDTASKINFO = 4
    _RUSAGE_INFO_V0 = 0
    try:
        _libproc = ctypes.CDLL("libproc.dylib", use_errno=True)
        _libproc.proc_pidinfo.restype = ctypes.c_int
        _libproc.proc_pidinfo.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int,
        ]
        _libproc.proc_pid_rusage.restype = ctypes.c_int
        _libproc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    except OSError:  # pragma: no cover - libproc is always present on macOS
        _libproc = None

    def sample() -> Optional[MemorySample]:
        # ru_maxrss is in bytes on macOS
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / _MB
        current_mb = peak_mb
        footprint_mb = None
        if _libproc is not None:
            pid = os.getpid()
            info = _ProcTaskInfo()
            size = ctypes.sizeof(info)
            if _libproc.proc_pidinfo(pid, _PROC_PIDTASKINFO, 0, ctypes.byref(info), size) == size:
                current_mb = info.pti_resident_size / _MB
            ri = _RusageInfoV0()
            if _libproc.proc_pid_rusage(pid, _RUSAGE_INFO_V0, ctypes.byref(ri)) == 0:
                footprint_mb = ri.ri_phys_footprint / _MB
        return MemorySample(rss_mb=current_mb, peak_rss_mb=peak_mb, footprint_mb=footprint_mb)

# --------------------------------------------------------------------------
# Linux and other Unix
# --------------------------------------------------------------------------
else:
    import resource

    def sample() -> Optional[MemorySample]:
        # ru_maxrss is in kilobytes on Linux
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        current_mb = peak_mb
        try:
            with open("/proc/self/statm") as f:
                resident_pages = int(f.read().split()[1])
            current_mb = resident_pages * os.sysconf("SC_PAGE_SIZE") / _MB
        except (OSError, ValueError, IndexError):
            pass
        return MemorySample(rss_mb=current_mb, peak_rss_mb=peak_mb)
