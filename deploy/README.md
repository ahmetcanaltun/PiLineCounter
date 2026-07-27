# Running as a systemd service

Autostarts the counter on boot and restarts it on failure.

```bash
# 1. Install the unit file
sudo cp /home/pi/camera_module/deploy/camera_module.service /etc/systemd/system/

# 2. Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable --now camera_module

# 3. Check status and follow logs
sudo systemctl status camera_module
sudo journalctl -u camera_module -f
```

Adjust `User`, `Group` and the paths in the unit file if the project is not
installed at `/home/pi/camera_module`.

`EnvironmentFile` is prefixed with `-`, so the service starts normally when no
`.env` file exists — that file is only needed for the optional fleet
integration. After changing it:

```bash
sudo systemctl restart camera_module
```
