"""Tests for the HTTP surface in app.py."""


class TestInterface:
    def test_root_serves_the_page(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"<title>Counter</title>" in response.data

    def test_page_needs_no_server_side_templating(self, client):
        # index.html is a static file; a stray Jinja tag would ship to the
        # browser verbatim rather than being rendered.
        body = client.get("/").data
        assert b"{{" not in body and b"{%" not in body

    def test_former_pages_redirect_to_the_app(self, client):
        for path in ("/config", "/monitor"):
            response = client.get(path)
            assert response.status_code == 302
            assert response.headers["Location"].endswith("/")


class TestDataEndpoint:
    def test_reports_counts_and_stream_state(self, client):
        data = client.get("/api/data").get_json()
        assert data["counts"] == {"in": 7, "out": 3}
        assert data["fps"] == 9.7
        assert data["resolution"] == [854, 480]

    def test_includes_the_settings_the_page_boots_from(self, client):
        data = client.get("/api/data").get_json()
        assert data["monitor"] is True
        assert data["interval"] == 5.0

    def test_monitor_is_false_when_the_flag_is_absent(self, client):
        import app as flask_app

        flask_app.args.monitor = False
        assert client.get("/api/data").get_json()["monitor"] is False


class TestConfigEndpoint:
    def test_forwards_line_mode_and_direction(self, client, processor):
        response = client.post(
            "/api/config",
            json={
                "line": [10, 20, 30, 40],
                "mode": "vehicle",
                "flip_direction": True,
            },
        )
        assert response.status_code == 200
        assert processor.config_updates[-1] == {
            "line": [10, 20, 30, 40],
            "mode": "vehicle",
            "flip_direction": True,
        }

    def test_omitted_fields_are_passed_as_none(self, client, processor):
        # The page sends only what changed; None means "leave this alone".
        client.post("/api/config", json={"mode": "person"})
        assert processor.config_updates[-1]["line"] is None
        assert processor.config_updates[-1]["flip_direction"] is None

    def test_returns_the_resulting_state(self, client):
        body = client.post("/api/config", json={"mode": "person"}).get_json()
        assert body["status"] == "ok"
        assert "counts" in body["data"]


class TestRoiEndpoint:
    def test_forwards_the_region(self, client, processor):
        region = {"enabled": True, "x": 100, "y": 50, "width": 600, "height": 380}
        assert client.post("/api/roi", json=region).status_code == 200
        assert processor.roi_updates[-1] == region

    def test_accepts_the_exact_keys_the_page_sends(self, client, processor):
        # Guards the contract between index.html and update_roi().
        client.post(
            "/api/roi",
            json={
                "enabled": False,
                "x": 0,
                "y": 0,
                "width": 854,
                "height": 480,
            },
        )
        assert set(processor.roi_updates[-1]) == {
            "enabled",
            "x",
            "y",
            "width",
            "height",
        }


class TestCountersAndRecords:
    def test_reset_reaches_the_processor(self, client, processor):
        assert client.post("/api/reset", json={}).status_code == 200
        assert processor.resets == 1

    def test_records_are_returned_as_a_list(self, client):
        records = client.get("/api/records").get_json()
        assert isinstance(records, list)
        assert set(records[0]) == {"from", "to", "in", "out"}


class TestStandalone:
    def test_no_backend_integration_remains(self):
        """The app must not reach for a remote service or an .env file."""
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        source = (root / "app.py").read_text() + (root / "camera_processor.py").read_text()
        for symbol in ("ConfigSync", "dotenv", "API_BASE_URL", "DEVICE_TOKEN", "requests"):
            assert symbol not in source, f"{symbol} is back in the source"

    def test_importing_the_processor_has_no_side_effects(self):
        """Importing must not construct a camera or read config.json."""
        source = (
            __import__("pathlib").Path(__file__).resolve().parent.parent / "camera_processor.py"
        ).read_text()
        assert "\nprocessor = CameraProcessor(" not in source
