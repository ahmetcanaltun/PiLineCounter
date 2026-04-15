"""
Camera Processor Module - Traffic Counting Edge Device
High-performance camera capture and AI inference with mode-based filtering.
Runs as a daemon thread to avoid blocking the Flask server.
"""

import threading
import time
import json
import cv2
import numpy as np
from collections import defaultdict
from pathlib import Path

# Conditional imports for Pi vs development
try:
    from picamera2 import Picamera2
    PI_CAMERA_AVAILABLE = True
except ImportError:
    PI_CAMERA_AVAILABLE = False
    print("[WARN] Picamera2 not available - using OpenCV fallback")

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("[WARN] Ultralytics not available - detection disabled")


class CameraProcessor:
    """
    Manages camera capture, YOLO detection, object tracking, and line crossing counting.
    Supports mode-based filtering: 'person' or 'vehicle'.
    """

    CONFIG_PATH = Path(__file__).parent / "config.json"

    # COCO class definitions
    PERSON_CLASSES = [0]  # person
    VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck

    CLASS_NAMES = {
        0: 'person',
        2: 'car',
        3: 'motorcycle',
        5: 'bus',
        7: 'truck'
    }

    def __init__(self, resolution=(640, 480), framerate=30, video_path=None, interval_seconds=5):
        self.resolution = resolution
        self.framerate = framerate
        self.video_path = video_path
        self.interval_seconds = interval_seconds

        # Thread control
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # Frame buffer for streaming
        self._current_frame = None
        self._frame_lock = threading.Lock()

        # Counters
        self._count_in = 0
        self._count_out = 0

        # Virtual line coordinates [x1, y1, x2, y2]
        self._line = [0, resolution[1] // 2, resolution[0], resolution[1] // 2]

        # Detection mode: 'person' or 'vehicle'
        self._mode = 'person'

        # Flip IN/OUT direction
        self._flip_direction = False

        # ROI (Region of Interest) - None means full frame
        # Format: {'enabled': bool, 'x': int, 'y': int, 'width': int, 'height': int}
        self._roi = None

        # Tracking state
        self._track_history = defaultdict(list)
        self._counted_ids = set()

        # Camera and model
        self._camera = None
        self._model = None

        # FPS tracking
        self._fps = 0
        self._frame_times = []

        # Interval JSON records
        self._interval_in = 0
        self._interval_out = 0
        self._interval_start_time = None
        self._interval_records = []
        self._interval_lock = threading.Lock()

        # Load saved configuration
        self._load_config()

    def _load_config(self):
        """Load configuration from JSON file."""
        if self.CONFIG_PATH.exists():
            try:
                with open(self.CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    self._line = config.get('line', self._line)
                    self._mode = config.get('mode', 'person')
                    self._flip_direction = config.get('flip_direction', False)
                    counts = config.get('counts', {})
                    self._count_in = counts.get('in', 0)
                    self._count_out = counts.get('out', 0)
                    # Load ROI config
                    self._roi = config.get('roi', None)
                    roi_status = f", roi={self._roi['enabled']}" if self._roi else ""
                    print(f"[INFO] Config loaded: mode={self._mode}, flip={self._flip_direction}, line={self._line}{roi_status}")
            except Exception as e:
                print(f"[WARN] Failed to load config: {e}")

    def _save_config(self):
        """Save current configuration to JSON file."""
        config = {
            'line': self._line,
            'mode': self._mode,
            'flip_direction': self._flip_direction,
            'roi': self._roi,
            'counts': {
                'in': self._count_in,
                'out': self._count_out
            }
        }
        try:
            with open(self.CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to save config: {e}")

    def _get_active_classes(self):
        """Get YOLO class IDs based on current mode."""
        if self._mode == 'vehicle':
            return self.VEHICLE_CLASSES
        return self.PERSON_CLASSES

    def _init_camera(self):
        """Initialize camera - video file, Picamera2 on Pi, OpenCV fallback, or test mode."""
        if self.video_path:
            self._camera = cv2.VideoCapture(self.video_path)
            if self._camera.isOpened():
                self._test_mode = False
                print(f"[INFO] Video file opened: {self.video_path}")
            else:
                self._camera = None
                self._test_mode = True
                self._test_frame_count = 0
                print(f"[WARN] Could not open video file: {self.video_path} - TEST MODE")
        elif PI_CAMERA_AVAILABLE:
            self._camera = Picamera2()
            config = self._camera.create_preview_configuration(
                main={"size": self.resolution, "format": "BGR888"},
                buffer_count=4
            )
            self._camera.configure(config)
            self._camera.start()
            self._test_mode = False
            print(f"[INFO] Picamera2 initialized at {self.resolution}")
        else:
            self._camera = cv2.VideoCapture(0)
            if self._camera.isOpened():
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
                self._camera.set(cv2.CAP_PROP_FPS, self.framerate)
                self._test_mode = False
                print(f"[INFO] OpenCV VideoCapture initialized")
            else:
                self._camera = None
                self._test_mode = True
                self._test_frame_count = 0
                print(f"[INFO] No camera found - running in TEST MODE")

    def _init_model(self):
        """Initialize YOLO model."""
        if YOLO_AVAILABLE:
            self._model = YOLO('yolo11n_ncnn_model')
            print("[INFO] YOLOv11n NCNN model loaded")
        else:
            print("[WARN] Running without detection model")

    def _capture_frame(self):
        """Capture a frame from the camera."""
        if PI_CAMERA_AVAILABLE and self._camera and not self.video_path:
            frame = self._camera.capture_array("main")
            # Swap R and B channels
            return frame[:, :, ::-1].copy()
        elif self._camera:
            ret, frame = self._camera.read()
            if not ret or frame is None:
                return None
            h, w = frame.shape[:2]
            if (w, h) != self.resolution:
                frame = cv2.resize(frame, self.resolution)
            return frame
        return None

    def _ccw(self, A, B, C):
        """Check if three points are in counter-clockwise order."""
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    def _line_intersect(self, A, B, C, D):
        """Check if line segment AB intersects with line segment CD."""
        return self._ccw(A, C, D) != self._ccw(B, C, D) and self._ccw(A, B, C) != self._ccw(A, B, D)

    def _get_direction(self, prev_point, curr_point):
        """
        Determine crossing direction using vector cross product.
        Positive cross product = IN, Negative = OUT (flipped if flip_direction is True)
        """
        line_start = (self._line[0], self._line[1])
        line_end = (self._line[2], self._line[3])

        line_vec = np.array([line_end[0] - line_start[0], line_end[1] - line_start[1]])
        move_vec = np.array([curr_point[0] - prev_point[0], curr_point[1] - prev_point[1]])

        cross = line_vec[0] * move_vec[1] - line_vec[1] * move_vec[0]
        direction = 'in' if cross > 0 else 'out'

        if self._flip_direction:
            direction = 'out' if direction == 'in' else 'in'

        return direction

    def _process_frame(self, frame):
        """Run detection, tracking, and counting on a frame."""
        if frame is None:
            return None

        display_frame = frame.copy()

        line_start = (self._line[0], self._line[1])
        line_end = (self._line[2], self._line[3])

        # Draw virtual counting line (bright magenta for visibility)
        cv2.line(display_frame, line_start, line_end, (255, 0, 255), 2)

        # Draw endpoint circles (white with colored border)
        cv2.circle(display_frame, line_start, 6, (255, 255, 255), -1)
        cv2.circle(display_frame, line_start, 6, (255, 0, 255), 1)
        cv2.circle(display_frame, line_end, 6, (255, 255, 255), -1)
        cv2.circle(display_frame, line_end, 6, (255, 0, 255), 1)

        if self._model is None:
            self._draw_overlay(display_frame)
            return display_frame

        # ROI processing - crop frame if ROI is enabled
        roi_offset_x, roi_offset_y = 0, 0
        detect_frame = frame

        if self._roi and self._roi.get('enabled', False):
            rx = max(0, self._roi.get('x', 0))
            ry = max(0, self._roi.get('y', 0))
            rw = self._roi.get('width', frame.shape[1])
            rh = self._roi.get('height', frame.shape[0])

            # Clamp to frame bounds
            rx = min(rx, frame.shape[1] - 1)
            ry = min(ry, frame.shape[0] - 1)
            rw = min(rw, frame.shape[1] - rx)
            rh = min(rh, frame.shape[0] - ry)

            # Only crop if ROI is large enough (min 100x100)
            if rw >= 100 and rh >= 100:
                detect_frame = frame[ry:ry+rh, rx:rx+rw]
                roi_offset_x, roi_offset_y = rx, ry
                # Draw ROI rectangle
                cv2.rectangle(display_frame, (rx, ry), (rx+rw, ry+rh), (0, 200, 255), 2)
                cv2.putText(display_frame, "ROI", (rx + 5, ry + 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)

        # Run YOLO tracking with mode-based class filtering
        active_classes = self._get_active_classes()

        results = self._model.track(
            detect_frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=active_classes,
            verbose=False
        )

        if results[0].boxes is None or results[0].boxes.id is None:
            self._draw_overlay(display_frame)
            return display_frame

        boxes = results[0].boxes.xyxy.cpu().numpy()
        track_ids = results[0].boxes.id.cpu().numpy().astype(int)

        # Apply ROI offset to boxes
        if roi_offset_x > 0 or roi_offset_y > 0:
            boxes[:, 0] += roi_offset_x  # x1
            boxes[:, 1] += roi_offset_y  # y1
            boxes[:, 2] += roi_offset_x  # x2
            boxes[:, 3] += roi_offset_y  # y2
        classes = results[0].boxes.cls.cpu().numpy().astype(int)

        for box, track_id, cls in zip(boxes, track_ids, classes):
            x1, y1, x2, y2 = map(int, box)

            # Bottom-center point for line crossing detection
            cx = (x1 + x2) // 2
            cy = y2
            center = (cx, cy)

            # Update track history
            self._track_history[track_id].append(center)
            if len(self._track_history[track_id]) > 30:
                self._track_history[track_id].pop(0)

            # Check for line crossing
            if track_id not in self._counted_ids and len(self._track_history[track_id]) >= 2:
                prev_point = self._track_history[track_id][-2]
                curr_point = self._track_history[track_id][-1]

                if self._line_intersect(prev_point, curr_point, line_start, line_end):
                    direction = self._get_direction(prev_point, curr_point)

                    with self._lock:
                        if direction == 'in':
                            self._count_in += 1
                        else:
                            self._count_out += 1

                    self._counted_ids.add(track_id)
                    self._save_config()

                    with self._interval_lock:
                        if direction == 'in':
                            self._interval_in += 1
                        else:
                            self._interval_out += 1
                    print(f"[COUNT] {self.CLASS_NAMES.get(cls, 'obj')} #{track_id} -> {direction.upper()} | Total: IN={self._count_in}, OUT={self._count_out}")

            # Draw bounding box (cyan for active, green for counted)
            color = (0, 255, 100) if track_id in self._counted_ids else (255, 255, 0)
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 1)

            # Draw label with better contrast
            label = f"{self.CLASS_NAMES.get(cls, 'obj')} #{track_id}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.rectangle(display_frame, (x1, y1 - th - 4), (x1 + tw + 4, y1), (0, 0, 0), -1)
            cv2.putText(display_frame, label, (x1 + 2, y1 - 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            # Draw tracking trail (yellow gradient)
            points = self._track_history[track_id]
            for i in range(1, len(points)):
                thickness = max(1, int(np.sqrt(30 / float(i + 1)) * 1.2))
                cv2.line(display_frame, points[i-1], points[i], (0, 200, 255), thickness)

            # Draw center point (white with outline)
            cv2.circle(display_frame, center, 3, (0, 0, 0), -1)
            cv2.circle(display_frame, center, 2, (255, 255, 255), -1)

        self._draw_overlay(display_frame)
        return display_frame

    def _draw_overlay(self, frame):
        """Draw counters, mode, FPS, and direction indicator on frame."""
        h, w = frame.shape[:2]

        # Semi-transparent background for counters (top-left)
        overlay = frame.copy()
        cv2.rectangle(overlay, (4, 4), (95, 70), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # FPS indicator
        cv2.putText(frame, f"{self._fps:.1f} fps", (8, 18),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

        # Counter text
        cv2.putText(frame, f"IN:  {self._count_in}", (8, 38),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 100), 1)
        cv2.putText(frame, f"OUT: {self._count_out}", (8, 55),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 255), 1)

        # Mode indicator
        mode_text = "PERSON" if self._mode == 'person' else "VEHICLE"
        cv2.putText(frame, mode_text, (8, 68),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)

        # Direction arrows near the line
        line_cx = (self._line[0] + self._line[2]) // 2
        line_cy = (self._line[1] + self._line[3]) // 2

        # Calculate perpendicular direction for arrows
        dx = self._line[2] - self._line[0]
        dy = self._line[3] - self._line[1]
        length = np.sqrt(dx*dx + dy*dy)
        if length > 0:
            # Perpendicular unit vector
            px, py = -dy/length, dx/length

            # Arrow offset from line center
            offset = 30
            arrow_len = 15

            # IN arrow (green) - perpendicular direction based on flip
            if not self._flip_direction:
                in_x, in_y = int(line_cx + px * offset), int(line_cy + py * offset)
                in_end_x, in_end_y = int(in_x + px * arrow_len), int(in_y + py * arrow_len)
                out_x, out_y = int(line_cx - px * offset), int(line_cy - py * offset)
                out_end_x, out_end_y = int(out_x - px * arrow_len), int(out_y - py * arrow_len)
            else:
                out_x, out_y = int(line_cx + px * offset), int(line_cy + py * offset)
                out_end_x, out_end_y = int(out_x + px * arrow_len), int(out_y + py * arrow_len)
                in_x, in_y = int(line_cx - px * offset), int(line_cy - py * offset)
                in_end_x, in_end_y = int(in_x - px * arrow_len), int(in_y - py * arrow_len)

            # Draw IN label and arrow
            cv2.arrowedLine(frame, (in_end_x, in_end_y), (in_x, in_y), (0, 255, 100), 1, tipLength=0.4)
            cv2.putText(frame, "IN", (in_x - 8, in_y - 8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 100), 1)

            # Draw OUT label and arrow
            cv2.arrowedLine(frame, (out_end_x, out_end_y), (out_x, out_y), (100, 100, 255), 1, tipLength=0.4)
            cv2.putText(frame, "OUT", (out_x - 12, out_y - 8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 255), 1)

    def _check_interval(self):
        """Emit a JSON interval record if enough time has passed."""
        now = time.time()
        if self._interval_start_time is None:
            self._interval_start_time = now
            return

        if now - self._interval_start_time >= self.interval_seconds:
            from datetime import datetime
            with self._interval_lock:
                record = {
                    'from': datetime.fromtimestamp(self._interval_start_time).strftime('%Y-%m-%dT%H:%M:%S'),
                    'to': datetime.fromtimestamp(now).strftime('%Y-%m-%dT%H:%M:%S'),
                    'in': self._interval_in,
                    'out': self._interval_out,
                }
                self._interval_in = 0
                self._interval_out = 0
                self._interval_start_time = now
                self._interval_records.append(record)
                if len(self._interval_records) > 200:
                    self._interval_records.pop(0)
            print(f"[INTERVAL] {record}")

    def _run(self):
        """Main processing loop - runs in daemon thread."""
        self._init_camera()
        self._init_model()

        while self._running:
            frame_start = time.time()

            frame = self._capture_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            self._check_interval()
            processed = self._process_frame(frame)

            if processed is not None:
                _, buffer = cv2.imencode('.jpg', processed, [cv2.IMWRITE_JPEG_QUALITY, 92])
                with self._frame_lock:
                    self._current_frame = buffer.tobytes()

            # Calculate FPS
            self._frame_times.append(time.time() - frame_start)
            if len(self._frame_times) > 30:
                self._frame_times.pop(0)
            if self._frame_times:
                self._fps = 1.0 / (sum(self._frame_times) / len(self._frame_times))

            time.sleep(0.001)  # Small yield for other threads

        # Cleanup
        if PI_CAMERA_AVAILABLE and self._camera:
            self._camera.stop()
        elif self._camera:
            self._camera.release()

        print("[INFO] Camera processor stopped")

    def start(self):
        """Start the camera processor in a daemon thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[INFO] Camera processor started")

    def stop(self):
        """Stop the camera processor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_frame(self):
        """Get the current processed frame (thread-safe)."""
        with self._frame_lock:
            return self._current_frame

    def get_data(self):
        """Get current state data (thread-safe)."""
        with self._lock:
            return {
                'counts': {'in': self._count_in, 'out': self._count_out},
                'line': self._line.copy(),
                'mode': self._mode,
                'flip_direction': self._flip_direction,
                'roi': self._roi.copy() if self._roi else None
            }

    def reset_counts(self):
        """Reset counters to zero."""
        with self._lock:
            self._count_in = 0
            self._count_out = 0
            self._counted_ids.clear()
            self._track_history.clear()
            self._save_config()
        print("[INFO] Counters reset")

    def update_config(self, line=None, mode=None, flip_direction=None):
        """Update line coordinates, mode, and/or direction."""
        with self._lock:
            if line is not None:
                self._line = [int(x) for x in line]
                self._counted_ids.clear()  # Reset tracking for new line
                self._track_history.clear()
            if mode is not None and mode in ('person', 'vehicle'):
                if mode != self._mode:
                    self._mode = mode
                    self._counted_ids.clear()
                    self._track_history.clear()
            if flip_direction is not None:
                self._flip_direction = bool(flip_direction)
            self._save_config()
        print(f"[INFO] Config updated: mode={self._mode}, flip={self._flip_direction}, line={self._line}")

    def update_roi(self, roi):
        """Update ROI configuration."""
        with self._lock:
            if roi is None:
                self._roi = None
            else:
                self._roi = {
                    'enabled': bool(roi.get('enabled', False)),
                    'x': int(roi.get('x', 0)),
                    'y': int(roi.get('y', 0)),
                    'width': int(roi.get('width', self.resolution[0])),
                    'height': int(roi.get('height', self.resolution[1]))
                }
            self._save_config()
        roi_status = f"enabled={self._roi['enabled']}" if self._roi else "disabled"
        print(f"[INFO] ROI updated: {roi_status}")

    def get_latest_records(self, n=50):
        """Get last n interval records (thread-safe)."""
        with self._interval_lock:
            return list(self._interval_records[-n:])

    def get_resolution(self):
        """Get camera resolution."""
        return self.resolution


# Singleton instance - overridden by app.py with CLI args
processor = CameraProcessor(resolution=(854, 480), framerate=30)
