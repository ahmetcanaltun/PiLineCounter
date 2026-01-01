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

    def __init__(self, resolution=(640, 480), framerate=30):
        self.resolution = resolution
        self.framerate = framerate

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

        # Tracking state
        self._track_history = defaultdict(list)
        self._counted_ids = set()

        # Camera and model
        self._camera = None
        self._model = None

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
                    counts = config.get('counts', {})
                    self._count_in = counts.get('in', 0)
                    self._count_out = counts.get('out', 0)
                    print(f"[INFO] Config loaded: mode={self._mode}, line={self._line}")
            except Exception as e:
                print(f"[WARN] Failed to load config: {e}")

    def _save_config(self):
        """Save current configuration to JSON file."""
        config = {
            'line': self._line,
            'mode': self._mode,
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
        """Initialize camera - Picamera2 on Pi, OpenCV fallback otherwise."""
        if PI_CAMERA_AVAILABLE:
            self._camera = Picamera2()
            config = self._camera.create_preview_configuration(
                main={"size": self.resolution, "format": "RGB888"},
                buffer_count=4
            )
            self._camera.configure(config)
            self._camera.start()
            print(f"[INFO] Picamera2 initialized at {self.resolution}")
        else:
            self._camera = cv2.VideoCapture(0)
            self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self._camera.set(cv2.CAP_PROP_FPS, self.framerate)
            print(f"[INFO] OpenCV VideoCapture initialized")

    def _init_model(self):
        """Initialize YOLO model."""
        if YOLO_AVAILABLE:
            self._model = YOLO('yolov8n.pt')
            print("[INFO] YOLOv8n model loaded")
        else:
            print("[WARN] Running without detection model")

    def _capture_frame(self):
        """Capture a frame from the camera."""
        if PI_CAMERA_AVAILABLE and self._camera:
            frame = self._camera.capture_array("main")
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        elif self._camera:
            ret, frame = self._camera.read()
            return frame if ret else None
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
        Positive cross product = IN, Negative = OUT
        """
        line_start = (self._line[0], self._line[1])
        line_end = (self._line[2], self._line[3])

        line_vec = np.array([line_end[0] - line_start[0], line_end[1] - line_start[1]])
        move_vec = np.array([curr_point[0] - prev_point[0], curr_point[1] - prev_point[1]])

        cross = line_vec[0] * move_vec[1] - line_vec[1] * move_vec[0]
        return 'in' if cross > 0 else 'out'

    def _process_frame(self, frame):
        """Run detection, tracking, and counting on a frame."""
        if frame is None:
            return None

        display_frame = frame.copy()

        line_start = (self._line[0], self._line[1])
        line_end = (self._line[2], self._line[3])

        # Draw virtual counting line
        cv2.line(display_frame, line_start, line_end, (0, 255, 255), 3)

        # Draw endpoint circles
        cv2.circle(display_frame, line_start, 8, (0, 255, 0), -1)
        cv2.circle(display_frame, line_end, 8, (0, 0, 255), -1)

        if self._model is None:
            self._draw_overlay(display_frame)
            return display_frame

        # Run YOLO tracking with mode-based class filtering
        active_classes = self._get_active_classes()

        results = self._model.track(
            frame,
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
                        self._save_config()

                    self._counted_ids.add(track_id)
                    print(f"[COUNT] {self.CLASS_NAMES.get(cls, 'obj')} #{track_id} -> {direction.upper()} | Total: IN={self._count_in}, OUT={self._count_out}")

            # Draw bounding box
            color = (0, 255, 0) if track_id in self._counted_ids else (255, 128, 0)
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)

            # Draw label
            label = f"{self.CLASS_NAMES.get(cls, 'obj')} #{track_id}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(display_frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(display_frame, label, (x1 + 2, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Draw tracking trail
            points = self._track_history[track_id]
            for i in range(1, len(points)):
                thickness = int(np.sqrt(30 / float(i + 1)) * 2)
                cv2.line(display_frame, points[i-1], points[i], (0, 165, 255), thickness)

            # Draw center point
            cv2.circle(display_frame, center, 5, (0, 0, 255), -1)

        self._draw_overlay(display_frame)
        return display_frame

    def _draw_overlay(self, frame):
        """Draw counters and mode indicator on frame."""
        # Semi-transparent background for counters
        overlay = frame.copy()
        cv2.rectangle(overlay, (5, 5), (160, 100), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # Counter text
        cv2.putText(frame, f"IN:  {self._count_in}", (15, 35),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame, f"OUT: {self._count_out}", (15, 65),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 128, 255), 2)

        # Mode indicator
        mode_text = "PERSON" if self._mode == 'person' else "VEHICLE"
        cv2.putText(frame, mode_text, (15, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    def _run(self):
        """Main processing loop - runs in daemon thread."""
        self._init_camera()
        self._init_model()

        while self._running:
            frame = self._capture_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            processed = self._process_frame(frame)

            if processed is not None:
                _, buffer = cv2.imencode('.jpg', processed, [cv2.IMWRITE_JPEG_QUALITY, 85])
                with self._frame_lock:
                    self._current_frame = buffer.tobytes()

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
                'mode': self._mode
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

    def update_config(self, line=None, mode=None):
        """Update line coordinates and/or mode."""
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
            self._save_config()
        print(f"[INFO] Config updated: mode={self._mode}, line={self._line}")

    def get_resolution(self):
        """Get camera resolution."""
        return self.resolution


# Singleton instance
processor = CameraProcessor(resolution=(640, 480), framerate=30)
