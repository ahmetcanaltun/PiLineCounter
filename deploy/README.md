# Pi'da systemd autostart kurulumu

```bash
# 1. Service dosyasını kopyala
sudo cp /home/pi/camera_module/deploy/camera_module.service /etc/systemd/system/

# 2. systemd'ye bildir ve aç
sudo systemctl daemon-reload
sudo systemctl enable --now camera_module

# 3. Durumu kontrol et
sudo systemctl status camera_module
sudo journalctl -u camera_module -f
```

Servis otomatik olarak başlar ve Pi yeniden başlatılınca da açılır. Hatada 5 sn sonra yeniden başlatılır.

`.env` dosyası `EnvironmentFile` ile yüklenir. Değişiklik sonrası:
```bash
sudo systemctl restart camera_module
```
