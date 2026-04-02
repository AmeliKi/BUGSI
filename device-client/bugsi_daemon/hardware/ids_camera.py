"""IDS RGB camera driver using the IDS peak SDK.

Only works on machines with the IDS peak SDK installed.
On other platforms, open() raises NotImplementedError so the fallback
to MockCamera is triggered by cli.py.
"""
from __future__ import annotations

import atexit
import glob
import logging
import os
import threading

import numpy as np

from bugsi_daemon.hardware.base import StillCameraInterface, register_still_camera

logger = logging.getLogger(__name__)

# Common install locations for IDS peak CTI files (GenTL producers).
# The systemd service does not source /etc/profile.d/*.sh, so we must
# discover the path at runtime.
_CTI_SEARCH_GLOBS = [
    "/opt/ids/ids-peak*/lib/aarch64-linux-gnu/ids-peak/cti",
    "/opt/ids/ids-peak*/lib/x86_64-linux-gnu/ids-peak/cti",
    "/usr/lib/ids-peak/cti",
    "/usr/local/lib/ids-peak/cti",
]

# Same pattern for shared libraries.
_LIB_SEARCH_GLOBS = [
    "/opt/ids/ids-peak*/lib/aarch64-linux-gnu/ids-peak/lib",
    "/opt/ids/ids-peak*/lib/x86_64-linux-gnu/ids-peak/lib",
]


def _ensure_ids_env() -> None:
    """Set GENICAM_GENTL64_PATH and LD_LIBRARY_PATH if not already present.

    Scans well-known install locations so the driver works from systemd
    services that don't source /etc/profile.d/ids-rgb-camera.sh.
    """
    if not os.environ.get("GENICAM_GENTL64_PATH"):
        for pattern in _CTI_SEARCH_GLOBS:
            matches = sorted(glob.glob(pattern))
            if matches:
                cti_path = matches[-1]  # newest version
                os.environ["GENICAM_GENTL64_PATH"] = cti_path
                logger.info("Auto-detected GENICAM_GENTL64_PATH=%s", cti_path)
                break
        else:
            logger.warning(
                "Could not auto-detect GENICAM_GENTL64_PATH — "
                "set it manually or install IDS peak to /opt/ids/"
            )

    if "ids-peak" not in os.environ.get("LD_LIBRARY_PATH", ""):
        for pattern in _LIB_SEARCH_GLOBS:
            matches = sorted(glob.glob(pattern))
            if matches:
                lib_path = matches[-1]
                existing = os.environ.get("LD_LIBRARY_PATH", "")
                os.environ["LD_LIBRARY_PATH"] = (
                    f"{lib_path}:{existing}" if existing else lib_path
                )
                logger.info("Added IDS peak libs to LD_LIBRARY_PATH=%s", lib_path)
                break


@register_still_camera("ids_rgb")
class IDSRGBCamera(StillCameraInterface):
    """IDS RGB camera via ids_peak SDK."""

    FRAME_TIMEOUT_MS = 5_000
    PREFERRED_PIXEL_FORMATS = ("BayerRG8", "BGR8", "RGB8", "Mono8")
    _library_initialized = False
    _library_lock = threading.Lock()

    def __init__(
        self,
        resolution_width: int = 5136,
        resolution_height: int = 3856,
        camera_id: int = 0,
        autofocus_mode: str = "continuous",  # accepted but ignored (C-mount)
        exposure_us: float = 0,
        gain_db: float = 0.0,
        white_balance: str = "auto",
        balance_ratio_red: float = 0.0,
        balance_ratio_green: float = 0.0,
        balance_ratio_blue: float = 0.0,
        gamma: float = 1.0,
        black_level: float = 0.0,
        acquisition_frame_rate: float = 0.0,
        binning_horizontal: int = 1,
        binning_vertical: int = 1,
    ) -> None:
        self._width = resolution_width
        self._height = resolution_height
        self._camera_id = camera_id
        self._exposure_us = exposure_us
        self._gain_db = gain_db
        self._white_balance = white_balance
        self._balance_ratio_red = balance_ratio_red
        self._balance_ratio_green = balance_ratio_green
        self._balance_ratio_blue = balance_ratio_blue
        self._gamma = gamma
        self._black_level = black_level
        self._acquisition_frame_rate = acquisition_frame_rate
        self._binning_h = binning_horizontal
        self._binning_v = binning_vertical
        self._device = None
        self._datastream = None
        self._node_map_remote = None
        self._peak = None
        self._ipl = None
        self._sw_auto_exposure = False
        self._lock = threading.Lock()

    def open(self) -> None:
        with self._lock:
            self._open_locked()

    def _open_locked(self) -> None:
        if self._device is not None:
            return

        try:
            from ids_peak import ids_peak as peak
            from ids_peak_ipl import ids_peak_ipl as ipl
        except ImportError:
            raise NotImplementedError(
                "ids_peak not available — install the IDS peak SDK"
            )

        self._peak = peak
        self._ipl = ipl

        # Ensure env vars are set (systemd doesn't source profile.d)
        _ensure_ids_env()

        with IDSRGBCamera._library_lock:
            if not IDSRGBCamera._library_initialized:
                peak.Library.Initialize()
                IDSRGBCamera._library_initialized = True
                atexit.register(IDSRGBCamera._close_library)

        device_manager = peak.DeviceManager.Instance()
        device_manager.Update()

        if device_manager.Devices().empty():
            peak.Library.Close()
            raise RuntimeError(
                "No IDS cameras found. Is the camera connected and the USB driver loaded?"
            )

        descriptors = device_manager.Devices()
        idx = min(self._camera_id, descriptors.size() - 1)
        self._device = descriptors[idx].OpenDevice(peak.DeviceAccessType_Control)
        self._node_map_remote = self._device.RemoteDevice().NodeMaps()[0]

        model = ""
        try:
            model = self._node_map_remote.FindNode("DeviceModelName").Value()
        except Exception:
            model = "(unknown)"
        logger.info("IDS camera opened: %s", model)

        # Set pixel format
        for fmt_name in self.PREFERRED_PIXEL_FORMATS:
            try:
                self._node_map_remote.FindNode("PixelFormat").SetCurrentEntry(
                    self._node_map_remote.FindNode("PixelFormat").FindEntry(fmt_name)
                )
                logger.info("Pixel format set to %s", fmt_name)
                break
            except Exception:
                continue

        # Configure sensor parameters (binning first — changes payload size)
        self._apply_binning()
        self._apply_exposure_gain()
        self._apply_white_balance()
        self._apply_image_quality()
        self._apply_frame_rate()

        # Prepare datastream
        self._datastream = self._device.DataStreams()[0].OpenDataStream()
        payload_size = self._node_map_remote.FindNode("PayloadSize").Value()
        min_buffers = self._datastream.NumBuffersAnnouncedMinRequired()
        buffer_count = max(min_buffers, 3)

        for _ in range(buffer_count):
            buf = self._datastream.AllocAndAnnounceBuffer(payload_size)
            self._datastream.QueueBuffer(buf)

        # Start acquisition
        self._datastream.StartAcquisition()
        self._node_map_remote.FindNode("TLParamsLocked").SetValue(1)
        self._node_map_remote.FindNode("AcquisitionStart").Execute()
        self._node_map_remote.FindNode("AcquisitionStart").WaitUntilDone()

        if self._sw_auto_exposure:
            self._auto_calibrate()

        logger.info("IDSRGBCamera acquisition started (camera_id=%d)", self._camera_id)

    def _apply_exposure_gain(self) -> None:
        """Apply exposure time and gain settings via GenICam node map.

        A value of 0 means 'auto' — the camera's built-in auto-exposure
        and auto-gain are left enabled. Any positive value switches to
        manual mode and sets the requested value (clamped to camera range).

        Auto-mode nodes (ExposureAuto, GainAuto) may not exist on all
        camera models (e.g. U3-36PxXCP-C). Each node access is wrapped
        in its own try/except so that a missing auto node does not
        prevent the manual value from being applied.
        """
        nm = self._node_map_remote

        # Exposure
        if self._exposure_us > 0:
            try:
                nm.FindNode("ExposureAuto").SetCurrentEntry(
                    nm.FindNode("ExposureAuto").FindEntry("Off")
                )
            except Exception:
                logger.debug("ExposureAuto not available, skipping auto-disable")
            try:
                node = nm.FindNode("ExposureTime")
                val = max(node.Minimum(), min(self._exposure_us, node.Maximum()))
                node.SetValue(val)
                logger.info("Exposure set to %.0f us (manual)", val)
            except Exception:
                logger.warning("Could not set ExposureTime to %s us", self._exposure_us, exc_info=True)
        else:
            try:
                nm.FindNode("ExposureAuto").SetCurrentEntry(
                    nm.FindNode("ExposureAuto").FindEntry("Continuous")
                )
                logger.info("Exposure set to auto (hardware)")
            except Exception:
                logger.info("ExposureAuto not available — will use software auto-exposure")
                self._sw_auto_exposure = True
                try:
                    node = nm.FindNode("ExposureTime")
                    initial = max(node.Minimum(), min(20000, node.Maximum()))
                    node.SetValue(initial)
                except Exception:
                    pass

        # Gain (ISO equivalent)
        if self._gain_db > 0:
            try:
                nm.FindNode("GainAuto").SetCurrentEntry(
                    nm.FindNode("GainAuto").FindEntry("Off")
                )
            except Exception:
                logger.debug("GainAuto not available, skipping auto-disable")
            try:
                node = nm.FindNode("Gain")
                val = max(node.Minimum(), min(self._gain_db, node.Maximum()))
                node.SetValue(val)
                logger.info("Gain set to %.1f dB (manual)", val)
            except Exception:
                logger.warning("Could not set Gain to %s dB", self._gain_db, exc_info=True)
        else:
            try:
                nm.FindNode("GainAuto").SetCurrentEntry(
                    nm.FindNode("GainAuto").FindEntry("Continuous")
                )
                logger.info("Gain set to auto (hardware)")
            except Exception:
                logger.info("GainAuto not available — will use software auto-exposure")
                self._sw_auto_exposure = True
                try:
                    node = nm.FindNode("Gain")
                    initial = max(node.Minimum(), min(2.0, node.Maximum()))
                    node.SetValue(initial)
                except Exception:
                    pass

    def _auto_calibrate(
        self,
        target_brightness: float = 128.0,
        tolerance: float = 25.0,
        max_iterations: int = 8,
    ) -> None:
        """Software auto-exposure for cameras without ExposureAuto/GainAuto.

        Captures test frames and adjusts ExposureTime and Gain until the
        mean brightness is within *tolerance* of *target_brightness*.
        Prefers increasing exposure over gain to minimise sensor noise.
        """
        nm = self._node_map_remote
        ipl = self._ipl

        try:
            exp_node = nm.FindNode("ExposureTime")
        except Exception:
            logger.warning("Auto-calibration aborted: ExposureTime node not found")
            return

        gain_node = None
        try:
            gain_node = nm.FindNode("Gain")
        except Exception:
            logger.debug("Gain node not available for auto-calibration")

        mean_brightness = 0.0
        for iteration in range(max_iterations):
            # Grab a test frame
            try:
                buf = self._datastream.WaitForFinishedBuffer(self.FRAME_TIMEOUT_MS)
                raw = ipl.Image.CreateFromSizeAndBuffer(
                    buf.PixelFormat(), buf.BasePtr(), buf.Size(),
                    buf.Width(), buf.Height(),
                )
                bgr = raw.ConvertTo(ipl.PixelFormatName_BGR8)
                frame = np.array(bgr.get_numpy_3D(), dtype=np.uint8)
                self._datastream.QueueBuffer(buf)
            except Exception:
                logger.warning("Auto-calibration: failed to capture test frame")
                break

            mean_brightness = float(frame.mean())
            logger.debug(
                "Auto-calibration [%d/%d]: brightness=%.1f (target=%.1f)",
                iteration + 1, max_iterations, mean_brightness, target_brightness,
            )

            if abs(mean_brightness - target_brightness) <= tolerance:
                break

            ratio = target_brightness / max(mean_brightness, 1.0)
            ratio = max(0.25, min(ratio, 4.0))

            cur_exp = exp_node.Value()
            new_exp = max(exp_node.Minimum(), min(cur_exp * ratio, exp_node.Maximum()))
            exp_node.SetValue(new_exp)

            # Exposure maxed but still too dark — increase gain
            if new_exp >= exp_node.Maximum() * 0.95 and ratio > 1.0 and gain_node:
                cur_gain = gain_node.Value()
                extra = 3.0 * (ratio - 1.0)
                new_gain = min(cur_gain + extra, gain_node.Maximum())
                gain_node.SetValue(new_gain)

            # Too bright — reduce gain first
            if ratio < 1.0 and gain_node and gain_node.Value() > gain_node.Minimum():
                new_gain = max(gain_node.Value() - 3.0, gain_node.Minimum())
                gain_node.SetValue(new_gain)
        else:
            logger.warning(
                "Auto-calibration did not converge after %d iterations (brightness=%.1f)",
                max_iterations, mean_brightness,
            )

        logger.info(
            "Auto-calibration result: exposure=%.0f us, gain=%.1f dB, brightness=%.1f",
            exp_node.Value(),
            gain_node.Value() if gain_node else 0.0,
            mean_brightness,
        )

    def _apply_binning(self) -> None:
        """Apply horizontal/vertical binning. Must be called before PayloadSize read."""
        nm = self._node_map_remote
        for axis, value in [("BinningHorizontal", self._binning_h),
                            ("BinningVertical", self._binning_v)]:
            if value > 1:
                try:
                    node = nm.FindNode(axis)
                    val = max(node.Minimum(), min(value, node.Maximum()))
                    node.SetValue(val)
                    logger.info("%s set to %d", axis, val)
                except Exception:
                    logger.warning("Could not set %s to %d", axis, value, exc_info=True)

    def _apply_white_balance(self) -> None:
        """Apply white balance settings via GenICam node map.

        white_balance='auto' -> BalanceWhiteAuto Continuous
        white_balance='once' -> BalanceWhiteAuto Once
        white_balance='off'  -> Manual mode, uses balance_ratio_* values
        """
        nm = self._node_map_remote
        mode_map = {"auto": "Continuous", "once": "Once", "off": "Off"}
        genicam_mode = mode_map.get(self._white_balance, "Continuous")

        try:
            nm.FindNode("BalanceWhiteAuto").SetCurrentEntry(
                nm.FindNode("BalanceWhiteAuto").FindEntry(genicam_mode)
            )
            logger.info("White balance set to %s (%s)", self._white_balance, genicam_mode)
        except Exception:
            logger.debug("BalanceWhiteAuto not available or mode %s not supported", genicam_mode)

        if self._white_balance == "off":
            for selector, ratio in [("Red", self._balance_ratio_red),
                                    ("Green", self._balance_ratio_green),
                                    ("Blue", self._balance_ratio_blue)]:
                if ratio > 0:
                    try:
                        nm.FindNode("BalanceRatioSelector").SetCurrentEntry(
                            nm.FindNode("BalanceRatioSelector").FindEntry(selector)
                        )
                        node = nm.FindNode("BalanceRatio")
                        val = max(node.Minimum(), min(ratio, node.Maximum()))
                        node.SetValue(val)
                        logger.info("BalanceRatio[%s] set to %.2f", selector, val)
                    except Exception:
                        logger.warning("Could not set BalanceRatio[%s]", selector, exc_info=True)

    def _apply_image_quality(self) -> None:
        """Apply gamma and black level settings."""
        nm = self._node_map_remote

        if self._gamma != 1.0:
            try:
                node = nm.FindNode("Gamma")
                val = max(node.Minimum(), min(self._gamma, node.Maximum()))
                node.SetValue(val)
                logger.info("Gamma set to %.2f", val)
            except Exception:
                logger.warning("Could not set Gamma to %.2f", self._gamma, exc_info=True)

        if self._black_level != 0.0:
            try:
                node = nm.FindNode("BlackLevel")
                val = max(node.Minimum(), min(self._black_level, node.Maximum()))
                node.SetValue(val)
                logger.info("BlackLevel set to %.2f", val)
            except Exception:
                logger.warning("Could not set BlackLevel to %.2f", self._black_level, exc_info=True)

    def _apply_frame_rate(self) -> None:
        """Apply acquisition frame rate limit. 0 = unlimited."""
        if self._acquisition_frame_rate <= 0:
            return
        nm = self._node_map_remote
        try:
            node = nm.FindNode("AcquisitionFrameRate")
            val = max(node.Minimum(), min(self._acquisition_frame_rate, node.Maximum()))
            node.SetValue(val)
            logger.info("AcquisitionFrameRate set to %.1f fps", val)
        except Exception:
            logger.warning(
                "Could not set AcquisitionFrameRate to %.1f",
                self._acquisition_frame_rate, exc_info=True,
            )

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._device is None:
            return

        peak = self._peak
        try:
            self._node_map_remote.FindNode("AcquisitionStop").Execute()
            self._node_map_remote.FindNode("TLParamsLocked").SetValue(0)
        except Exception:
            pass

        if self._datastream is not None:
            try:
                self._datastream.StopAcquisition(peak.AcquisitionStopMode_Default)
            except Exception:
                pass
            try:
                self._datastream.Flush(peak.DataStreamFlushMode_DiscardAll)
            except Exception:
                pass
            for buf in self._datastream.AnnouncedBuffers():
                try:
                    self._datastream.RevokeBuffer(buf)
                except Exception:
                    pass

        # Release device handles but keep Library initialized so camera
        # can be reopened without restarting the daemon.  Library.Close()
        # is only called via atexit on process exit.
        self._device = None
        self._datastream = None
        self._node_map_remote = None
        logger.info("IDSRGBCamera closed")

    @classmethod
    def _close_library(cls) -> None:
        """Close the IDS peak library on process exit."""
        with cls._library_lock:
            if cls._library_initialized:
                try:
                    from ids_peak import ids_peak as peak
                    peak.Library.Close()
                except Exception:
                    pass
                cls._library_initialized = False

    def capture(self) -> np.ndarray:
        with self._lock:
            if self._device is None:
                raise RuntimeError("Camera not open. Call open() first.")

            ipl = self._ipl
            buffer = self._datastream.WaitForFinishedBuffer(self.FRAME_TIMEOUT_MS)

            raw_image = ipl.Image.CreateFromSizeAndBuffer(
                buffer.PixelFormat(),
                buffer.BasePtr(),
                buffer.Size(),
                buffer.Width(),
                buffer.Height(),
            )
            bgr_image = raw_image.ConvertTo(ipl.PixelFormatName_BGR8)
            frame = np.array(bgr_image.get_numpy_3D(), dtype=np.uint8).copy()

            self._datastream.QueueBuffer(buffer)
            return frame

    def is_open(self) -> bool:
        return self._device is not None
