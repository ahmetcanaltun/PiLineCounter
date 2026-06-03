# Traffic Counting Edge Device

Real-time traffic/people counting system for Raspberry Pi 5 with Camera Module v3. Uses YOLOv11n (NCNN optimized) + ByteTrack for detection and tracking with a web-based interface. Achieves ~10 FPS on Raspberry Pi 5.

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
| `--monitor` | off | Enable interval monitor at `/monitor` |
| `--interval N` | 5 | Interval seconds for JSON records |

### Pages

| URL | Description |
|-----|-------------|
| `/` | Dashboard — live stream |
| `/config` | Configuration — line editor, ROI, mode, direction |
| `/monitor` | Interval monitor (requires `--monitor`) |

## API Reference

### GET `/api/data`

Returns current state.

```json
{
  "counts": {"in": 42, "out": 38},
  "line": [427, 0, 427, 480],
  "mode": "person",
  "flip_direction": false,
  "roi": {"enabled": false, "x": 0, "y": 0, "width": 854, "height": 480}
}
```

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

Settings are stored in `config.json` (auto-created, gitignored). See `config.json.example` for structure.

```json
{
  "line": [427, 0, 427, 480],
  "mode": "person",
  "flip_direction": false
}
```

| Field | Description |
|-------|-------------|
| `line` | Virtual line coordinates `[x1, y1, x2, y2]` |
| `mode` | `"person"` (class 0) or `"vehicle"` (classes 2, 3, 5, 7) |
| `flip_direction` | Swap IN/OUT assignment |

## Counting Logic

- **Reference Point**: Bottom-center of bounding box (foot/wheel position)
- **Direction Detection**: Vector cross-product relative to line direction
- **flip_direction**: Swaps which side counts as IN vs OUT

## Run as Service

### Create systemd Service

```bash
sudo nano /etc/systemd/system/traffic-counter.service
```

```ini
[Unit]
Description=Traffic Counter
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/camera_module
Environment=PATH=/home/pi/camera_module/venv/bin
ExecStart=/home/pi/camera_module/venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Enable Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable traffic-counter
sudo systemctl start traffic-counter
```

### View Logs

```bash
journalctl -u traffic-counter -f
```

Or use the desktop launcher: `bash start.sh`

## Project Structure

```
camera_module/
├── app.py                 # Flask web server & API
├── camera_processor.py    # Camera + AI processing thread
├── config.json.example    # Config template
├── requirements.txt       # Python dependencies
├── start.sh               # Pi desktop launcher
├── README.md
└── templates/
    ├── index.html         # Dashboard (live stream)
    ├── config.html        # Configuration UI
    └── monitor.html       # Interval monitor
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
