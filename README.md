# Traffic Counting Edge Device

Real-time traffic/people counting system for Raspberry Pi 5 with Camera Module v3. Uses YOLOv8 + ByteTrack for detection and tracking with a web-based admin panel.

## Features

- **Real-time Detection**: YOLOv8n with ByteTrack multi-object tracking
- **Dual Mode**: Person counting (libraries, retail) or Vehicle counting (parking, traffic)
- **Virtual Line Crossing**: Configurable counting line with IN/OUT direction detection
- **Web Dashboard**: Live MJPEG stream with real-time counters
- **Drag & Drop Config**: Interactive line positioning on live video
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

### 4. Verify Camera

```bash
libcamera-hello --list-cameras
```

## Usage

### Start the Server

```bash
python app.py
```

Access the web interface at `http://<pi-ip>:5000`

### Pages

| URL | Description |
|-----|-------------|
| `/` | Dashboard - Live stream with IN/OUT counters |
| `/config` | Configuration - Drag endpoints to position counting line |

## API Reference

### GET `/api/data`

Returns current state.

```json
{
  "counts": {"in": 42, "out": 38},
  "line": [0, 240, 640, 240],
  "mode": "person"
}
```

### POST `/api/config`

Update line coordinates and/or detection mode.

```bash
curl -X POST http://localhost:5000/api/config \
  -H "Content-Type: application/json" \
  -d '{"line": [100, 200, 540, 200], "mode": "vehicle"}'
```

### POST `/api/reset`

Reset counters to zero.

```bash
curl -X POST http://localhost:5000/api/reset
```

### GET `/video_feed`

MJPEG video stream. Embed in HTML:

```html
<img src="http://<pi-ip>:5000/video_feed">
```

## Configuration

Settings are stored in `config.json`:

```json
{
  "line": [0, 240, 640, 240],
  "mode": "person",
  "counts": {"in": 0, "out": 0}
}
```

| Field | Description |
|-------|-------------|
| `line` | Virtual line coordinates `[x1, y1, x2, y2]` |
| `mode` | `"person"` (class 0) or `"vehicle"` (classes 2,3,5,7) |
| `counts` | Persistent IN/OUT counters |

## Counting Logic

- **Reference Point**: Bottom-center of bounding box (foot position)
- **Direction Detection**: Vector cross-product relative to line direction
- **IN**: Objects crossing right-to-left (relative to line vector)
- **OUT**: Objects crossing left-to-right

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

## Project Structure

```
camera_module/
├── app.py                 # Flask web server
├── camera_processor.py    # Camera + AI processing thread
├── config.json            # Persistent configuration
├── requirements.txt       # Python dependencies
├── README.md
└── templates/
    ├── index.html         # Dashboard page
    └── config.html        # Configuration page
```

## Performance

| Metric | Value |
|--------|-------|
| Resolution | 640x480 |
| Frame Rate | ~15-20 FPS (with inference) |
| Model | YOLOv8n (nano) |
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

- Reduce resolution in `camera_processor.py`
- Use `yolov8n.pt` (nano) instead of larger models
- Ensure adequate cooling for Pi 5

### Model download fails

```bash
# Manually download YOLOv8n
pip install ultralytics
yolo export model=yolov8n.pt format=onnx
```

## License

MIT
