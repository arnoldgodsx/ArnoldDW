# Arnold DW

YouTube video ve ses indirme masaüstü uygulaması. Python + [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) ile yazıldı, [yt-dlp](https://github.com/yt-dlp/yt-dlp) kullanır, [PyInstaller](https://pyinstaller.org/) ile tek klasörlük bir Windows uygulaması olarak paketlenir.

## Özellikler

- Link yapıştırınca otomatik önizleme (kapak, başlık, kanal, süre)
- MP4 (video) veya MP3 (ses) olarak indirme
- Video kalitesi, kaynağın gerçekte sunduğu çözünürlüklerle sınırlı (örn. video 1080p ise 4K/1440p seçeneği çıkmaz)
- MP3 için bit hızı seçimi (320 / 192 / 128 kbps)
- İndirme konumu seçilebilir, bir sonraki açılışta hatırlanır
- İndirme sırasında ilerleme yüzdesi, hız ve kalan süre; indirme iptal edilebilir
- Video sesi her zaman AAC olarak birleştirilir (bazı oynatıcıların Opus sesi çalmadığı sorunun önüne geçmek için)

## Kurulum

```bash
git clone git@github.com:merdogdux/ArnoldDW.git
cd ArnoldDW
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

`bin/ffmpeg.exe` depoya dahil edilmiştir; ayrıca bir ffmpeg kurulumu gerekmez.

## Çalıştırma

```bash
python app.py
```

## .exe olarak derleme

```bash
pyinstaller "Arnold DW.spec" --noconfirm
```

Çıktı `dist/Arnold DW/Arnold DW.exe` olarak oluşur.

## Kullanılan teknolojiler

Python, CustomTkinter, yt-dlp, Pillow, requests, PyInstaller, ffmpeg.
