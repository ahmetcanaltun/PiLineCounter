"""
Flask Web Application - Traffic Counting Edge Device
Provides web interface for live streaming and configuration.
"""

import argparse

from flask import Flask, redirect, send_from_directory, Response, jsonify, request
from camera_processor import CameraProcessor

app = Flask(__name__)
processor = None
args = None


def generate_frames():
    """Generator for MJPEG streaming."""
    import time
    while True:
        frame = processor.get_frame()
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            time.sleep(0.01)


@app.route('/')
def index():
    """The web interface - a static page that boots from /api/data."""
    return send_from_directory(app.root_path, 'index.html')


@app.route('/config')
@app.route('/monitor')
def legacy_pages():
    """The former separate pages are now panels of the main interface."""
    return redirect('/')


@app.route('/video_feed')
def video_feed():
    """MJPEG video stream endpoint."""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/data')
def api_data():
    """Everything the interface needs: counts, line, mode, roi, fps, settings."""
    return jsonify({
        **processor.get_data(),
        'monitor': bool(args and args.monitor),
        'interval': args.interval if args else 5,
    })


@app.route('/api/reset', methods=['POST'])
def api_reset():
    """Reset counters to zero."""
    processor.reset_counts()
    return jsonify({'status': 'ok'})


@app.route('/api/config', methods=['POST'])
def api_config():
    """Update line coordinates, mode, and/or direction."""
    data = request.get_json()

    line = data.get('line')
    mode = data.get('mode')
    flip_direction = data.get('flip_direction')

    processor.update_config(line=line, mode=mode, flip_direction=flip_direction)

    return jsonify({'status': 'ok', 'data': processor.get_data()})


@app.route('/api/roi', methods=['POST'])
def api_roi():
    """Update ROI (Region of Interest) configuration."""
    data = request.get_json()
    processor.update_roi(data)
    return jsonify({'status': 'ok', 'data': processor.get_data()})


@app.route('/api/records')
def api_records():
    """Get latest interval records."""
    return jsonify(processor.get_latest_records())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Traffic Counter')
    parser.add_argument('--video', type=str, default=None,
                        help='Video file path (default: live camera)')
    parser.add_argument('--monitor', action='store_true',
                        help='Enable JSON monitor at /monitor')
    parser.add_argument('--interval', type=float, default=5.0,
                        help='Interval seconds for JSON records (default: 5)')
    args = parser.parse_args()

    processor = CameraProcessor(resolution=(854, 480), framerate=30,
                                 video_path=args.video,
                                 interval_seconds=args.interval)
    processor.start()

    try:
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    finally:
        processor.stop()
