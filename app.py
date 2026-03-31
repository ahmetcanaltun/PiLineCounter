"""
Flask Web Application - Traffic Counting Edge Device
Provides web interface for live streaming and configuration.
"""

from flask import Flask, render_template, Response, jsonify, request
from camera_processor import processor

app = Flask(__name__)


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
    """Dashboard page with live stream and counters."""
    return render_template('index.html')


@app.route('/config')
def config_page():
    """Configuration page with interactive line editor."""
    data = processor.get_data()
    resolution = processor.get_resolution()
    return render_template('config.html',
                         line=data['line'],
                         mode=data['mode'],
                         flip_direction=data['flip_direction'],
                         roi=data['roi'],
                         width=resolution[0],
                         height=resolution[1])


@app.route('/video_feed')
def video_feed():
    """MJPEG video stream endpoint."""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/data')
def api_data():
    """Get current counts, line, and mode."""
    return jsonify(processor.get_data())


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


if __name__ == '__main__':
    processor.start()
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    finally:
        processor.stop()
