# Traffic Counting Edge Device

Real-time traffic/people counting system for Raspberry Pi 5 with Camera Module v3. Uses YOLOv11n (NCNN optimized) + ByteTrack for detection and tracking with a web-based interface. Achieves ~10 FPS on Raspberry Pi 5.

Runs entirely on the device — no cloud service, no account, no internet connection required. Point it at a doorway or a road, draw a line in the browser, and it counts what crosses it.

## Features

- **Real-time Detection**: YOLOv11n NCNN with ByteTrack multi-object tracking
- **Dual Mode**: Person counting (libraries, retail) or Vehicle counting (parking, traffic)
- **Virtual Line Crossing**: Configurable counting line with IN/OUT direction detection
- **ROI Support**: Optional Region of Interest to restrict detection area
- **Web Interface**: Live MJPEG stream, interactive config, and interval monitor
- **Drag & Drop Config**: Interactive line/ROI positioning on live video
- **Interval Recording**: Periodic IN/OUT snapshots (configurable interval)
- **Persistent Storage**: Configuration and counts survive reboots

## Hardware Requirements

- Raspberry Pi 5 (4GB+ RAM recommended)
- Camera Module v3 (Standard or Wide)
- MicroSD card (32GB+ recommended)

## Installation

### 1. System Dependencies (Pi OS)

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv libcamera-dev
```

### 2. Create Virtual Environment

```bash
cd ~/camera_module
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Packages

```bash
pip install -r requirements.txt
```

### 4. Export YOLO Model to NCNN

```bash
python -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='ncnn')"
```

### 5. Verify Camera

```bash
libcamera-hello --list-cameras
```

## Usage

### Start the Server

```bash
# Live camera
python app.py

# Video file
python app.py --video /path/to/video.mp4

# With interval monitor (default: 5s interval)
python app.py --monitor

# Custom interval
python app.py --monitor --interval 10
```

Access the web interface at `http://<pi-ip>:5000`

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--video PATH` | — | Use video file instead of camera |
| `--monitor` | off | Show the interval records panel in the interface |
| `--interval N` | 5 | Interval seconds for JSON records |

### Interface

The whole app lives on one page at `http://<pi-ip>:5000`:

- **Live view** with the counting line and region of interest drawn on top of the stream
- **Drag the line endpoints** directly on the video, or type exact pixel coordinates
- **Counters** for in, out and net, updating once per second
- **Detection controls** — people or vehicles, and a switch to swap which side counts as in
- **Region of interest** — draw a box on the video to restrict detection and gain frame rate
- **Interval records** table when started with `--monitor`

Every change is applied and persisted immediately; there is no save button. `/config` and
`/monitor` redirect to `/` and remain only so old bookmarks keep working.

## API Reference

### GET `/api/data`

Returns current state.

```json
{
  "counts": {"in": 42, "out": 38},
  "line": [427, 0, 427, 480],
  "mode": "person",
  "flip_direction": false,
  "roi": {"enabled": false, "x": 0, "y": 0, "width": 854, "height": 480},
  "fps": 9.8,
  "resolution": [854, 480],
  "monitor": false,
  "interval": 5
}
```

The interface boots entirely from this endpoint — resolution, current line, mode and
settings all come from here, so `index.html` needs no server-side templating.

### POST `/api/config`

Update line coordinates, detection mode, and/or direction.

```bash
curl -X POST http://localhost:5000/api/config \
  -H "Content-Type: application/json" \
  -d '{"line": [427, 0, 427, 480], "mode": "person", "flip_direction": false}'
```

### POST `/api/roi`

Update Region of Interest.

```bash
curl -X POST http://localhost:5000/api/roi \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "x": 100, "y": 50, "width": 600, "height": 380}'
```

### POST `/api/reset`

Reset counters to zero.

```bash
curl -X POST http://localhost:5000/api/reset
```

### GET `/api/records`

Get last 50 interval records (requires `--monitor`).

```json
[
  {"from": "2026-04-01T14:23:00", "to": "2026-04-01T14:23:05", "in": 3, "out": 1},
  ...
]
```

## Configuration

Settings are stored in `config.json`, created automatically on first run and gitignored:

```json
{
  "line": [427, 0, 427, 480],
  "mode": "person",
  "flip_direction": false,
  "roi": null,
  "counts": {"in": 0, "out": 0}
}
```

| Field | Description |
|-------|-------------|
| `line` | Virtual line coordinates `[x1, y1, x2, y2]` |
| `mode` | `"person"` (class 0) or `"vehicle"` (classes 2, 3, 5, 7) |
| `flip_direction` | Swap IN/OUT assignment |
| `roi` | ROI dict `{enabled, x, y, width, height}` or `null` |
| `counts` | Persistent IN/OUT counters (reset on startup) |

## Counting Logic

- **Reference Point**: Bottom-center of bounding box (foot/wheel position)
- **Direction Detection**: Vector cross-product relative to line direction
- **flip_direction**: Swaps which side counts as IN vs OUT

## Run as Service

To start the counter on boot, create `/etc/systemd/system/camera_module.service`:

```ini
[Unit]
Description=Camera Module - people and vehicle counting service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/camera_module
ExecStart=/home/pi/camera_module/venv/bin/python -u /home/pi/camera_module/app.py
Restart=on-failure
RestartSec=5

# config.json is rewritten at runtime, so the app needs write access
ProtectSystem=full
ReadWritePaths=/home/pi/camera_module

[Install]
WantedBy=multi-user.target
```

Adjust `User` and the paths if the project lives somewhere else, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now camera_module
journalctl -u camera_module -f
```

## Project Structure

```
camera_module/
├── app.py                 # Flask server: routes, MJPEG stream, REST API
├── camera_processor.py    # Capture, inference, tracking and counting thread
├── index.html             # The entire web interface (no build step, no CDN)
├── requirements.txt
└── README.md
```

## Performance

| Metric | Value |
|--------|-------|
| Resolution | 854x480 |
| Frame Rate | ~10 FPS (with NCNN inference) |
| Model | YOLOv11n NCNN |
| Tracker | ByteTrack |

## Troubleshooting

### Camera not detected

```bash
# Check camera connection
libcamera-hello

# Verify in config.txt
sudo nano /boot/firmware/config.txt
# Ensure: camera_auto_detect=1
```

### Low frame rate

- Ensure NCNN model is used (`yolo11n_ncnn_model/` folder must exist)
- Re-export if missing: `python -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='ncnn')"`
- Reduce resolution in `camera_processor.py`
- Ensure adequate cooling for Pi 5

### Model not found

```bash
# Export YOLOv11n to NCNN format
python -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='ncnn')"
# This creates yolo11n_ncnn_model/ directory
```

## License

MIT
