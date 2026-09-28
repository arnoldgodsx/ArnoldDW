# Üçüncü taraf bildirimleri

Arnold DW'nin Windows derlemesi Python uygulama dosyalarına ek olarak aşağıdaki çalışma zamanı bileşenlerini kullanabilir. “Denetlenen sürüm”, 2026-09-28 tarihinde HQ paylaşımlı Python ortamında görülen sürümdür; sürüm aralığı ise depo gereksiniminde ilan edilen sınırdır. Gereksinimler sabitlenmediği için yeni kurulum veya derleme farklı sürümler getirebilir. Yayımlanacak gerçek paketin yazılım envanteri build çıktısından ayrıca doğrulanmalıdır.

## Uygulama ve Python çalışma zamanı

### Python

- **Sürüm:** 3.12.14 (denetlenen HQ çalışma zamanı); projede alt/üst sürüm aralığı sabitlenmemiştir.
- **Lisans:** Python Software Foundation License 2.0 (PSF-2.0).
- **Proje:** [python.org](https://www.python.org/) · [CPython kaynak kodu](https://github.com/python/cpython).
- **Telif:** Copyright © 2001 Python Software Foundation; Python lisans dosyasında ayrıca önceki Python katkı sahipleri ve gömülü bileşenler belirtilir.
- **Tam metin:** [licenses/Python-PSF-2.0.txt](licenses/Python-PSF-2.0.txt), HQ Python 3.12.14 dağıtımından kopyalanmıştır.

### Tcl ve Tk

- **Sürüm:** Tcl 8.6.12 (HQ Python çalışma zamanındaki Tcl patchlevel); Tk 8.6 serisi.
- **Lisans:** Projedeki `license.terms` koşulları (BSD benzeri, telif ve bildirimlerin korunmasını gerektirir).
- **Proje:** [Tcl](https://github.com/tcltk/tcl) · [Tk](https://github.com/tcltk/tk).
- **Telif:** Regents of the University of California, Sun Microsystems, Scriptics, ActiveState, Apple ve diğer katkı sahipleri; her dosyadaki telif bildirimleri geçerlidir.
- **Tam metin:** [licenses/Tcl-license.terms](licenses/Tcl-license.terms) ve [licenses/Tk-license.terms](licenses/Tk-license.terms). Tk metni dağıtılan HQ Python Tcl/Tk ağacından, Tcl metni resmi Tcl deposundan alınmıştır.

## Python paketleri

### yt-dlp

- **Sürüm aralığı:** `yt-dlp>=2024.12.23`; denetlenen sürüm `2026.8.19`.
- **Lisans:** Unlicense.
- **Proje:** [github.com/yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp).
- **Telif:** Proje katkı sahipleri; Unlicense telif hakkından feragat bildirimidir.
- **Tam metin:** [licenses/yt-dlp-Unlicense.txt](licenses/yt-dlp-Unlicense.txt), resmi proje deposundan alınmıştır. Bu bildirim yalnızca kurulan Python paketinin Unlicense kapsamını belirtir; ayrı yt-dlp yayın ikililerinde bulunabilecek diğer projelerin lisanslarını Arnold DW'ye uygulanacak şekilde varsaymaz.

### CustomTkinter

- **Sürüm aralığı:** `customtkinter>=5.2.2`; denetlenen sürüm `6.0.0`.
- **Lisans:** Wheel içindeki tam `LICENSE` MIT metnidir; PyPI METADATA alanı ise CC0-1.0 der. Upstream `setup.cfg` de CC0 yazar ve MIT sınıflandırıcısı içerir. Tespit ettiğimiz dağıtımda tam metni bulunan lisans MIT'tir; kaynak metadata çelişkisini sürüm sahibiyle teyit edin.
- **Proje:** [github.com/TomSchimansky/CustomTkinter](https://github.com/TomSchimansky/CustomTkinter).
- **Telif:** Copyright © 2023 Tom Schimansky.
- **Tam metin:** [licenses/CustomTkinter-MIT.txt](licenses/CustomTkinter-MIT.txt) wheel'deki dosyadır. Metadata beyanının tam CC0 metni [licenses/CustomTkinter-CC0-1.0-legalcode.html](licenses/CustomTkinter-CC0-1.0-legalcode.html) dosyasındadır. Bu iki beyanın hangi lisansla kullanılacağını yayın öncesi upstream'den teyit edin. Paket varlıkları Roboto font dosyalarını da içerir (aşağıdaki Roboto kaydı).

### Pillow

- **Sürüm aralığı:** `pillow>=10.0.0`; denetlenen sürüm `12.3.0`.
- **Lisans:** MIT-CMU / HPND ve lisans dosyasında açıklanan üçüncü taraf bileşen lisansları.
- **Proje:** [github.com/python-pillow/Pillow](https://github.com/python-pillow/Pillow).
- **Telif:** Secret Labs AB, Fredrik Lundh, Jeffrey “Alex” Clark ve katkı sahipleri; tam atıflar lisans dosyasındadır.
- **Tam metin:** [licenses/Pillow-MIT-CMU-HPND.txt](licenses/Pillow-MIT-CMU-HPND.txt), kurulu wheel'den kopyalanmıştır.

### Requests

- **Sürüm aralığı:** `requests>=2.31.0`; denetlenen sürüm `2.34.2`.
- **Lisans:** Apache-2.0.
- **Proje:** [github.com/psf/requests](https://github.com/psf/requests).
- **Telif:** Copyright © 2019 Kenneth Reitz.
- **Tam metin ve atıf:** [licenses/requests-Apache-2.0.txt](licenses/requests-Apache-2.0.txt) ve [licenses/requests-NOTICE.txt](licenses/requests-NOTICE.txt), Requests wheel'inden alınmıştır.

### urllib3

- **Sürüm aralığı:** Requests 2.34.2 bildirimi `urllib3>=1.26,<3` ister; denetlenen sürüm `2.8.0`.
- **Lisans:** MIT.
- **Proje:** [github.com/urllib3/urllib3](https://github.com/urllib3/urllib3).
- **Telif:** Copyright © 2008–2020 Andrey Petrov ve katkı sahipleri (dağıtımda yazdığı biçimiyle).
- **Tam metin:** [licenses/urllib3-MIT.txt](licenses/urllib3-MIT.txt), urllib3 resmi deposundan alınmıştır.

### certifi

- **Sürüm aralığı:** Requests 2.34.2 bildirimi `certifi>=2023.5.7` ister; denetlenen sürüm `2026.7.22`.
- **Lisans:** MPL-2.0; paket ayrıca Mozilla CA sertifika demetini taşır.
- **Proje:** [github.com/certifi/python-certifi](https://github.com/certifi/python-certifi).
- **Telif:** Kenneth Reitz ve kök sertifikaların ilgili sahipleri; sertifika kaynakları ve bildirimler tam metindedir.
- **Tam metin:** [licenses/certifi-MPL-2.0.txt](licenses/certifi-MPL-2.0.txt), kurulu wheel'den kopyalanmıştır.

### charset-normalizer

- **Sürüm aralığı:** Requests 2.34.2 bildirimi `charset_normalizer>=2,<4` ister; denetlenen sürüm `3.5.1`.
- **Lisans:** MIT.
- **Proje:** [github.com/jawah/charset_normalizer](https://github.com/jawah/charset_normalizer).
- **Telif:** Copyright © 2025 Ahmed R. Tahri.
- **Tam metin:** [licenses/charset-normalizer-MIT.txt](licenses/charset-normalizer-MIT.txt), kurulu wheel'den kopyalanmıştır.

### idna

- **Sürüm aralığı:** Requests 2.34.2 bildirimi `idna>=2.5,<4` ister; denetlenen sürüm `3.20`.
- **Lisans:** BSD-3-Clause.
- **Proje:** [github.com/kjd/idna](https://github.com/kjd/idna).
- **Telif:** Copyright © 2013–2026 Kim Davies ve katkı sahipleri.
- **Tam metin:** [licenses/idna-BSD-3-Clause.txt](licenses/idna-BSD-3-Clause.txt), kurulu wheel'den kopyalanmıştır.

### Instaloader

- **Sürüm aralığı:** `instaloader>=4.13.0`; denetlenen sürüm `4.15.3`.
- **Lisans:** MIT.
- **Proje:** [github.com/instaloader/instaloader](https://github.com/instaloader/instaloader).
- **Telif:** Copyright © 2016–2020 Alexander Graf ve André Koch-Kramer.
- **Tam metin:** [licenses/Instaloader-MIT.txt](licenses/Instaloader-MIT.txt), kurulu wheel'den kopyalanmıştır.

### Mutagen — paket envanterinde doğrulanmalı

- **Sürüm:** HQ ortamında bildirilen `1.48.1`; CX-1'in gereksinim listesinde doğrudan yer almıyor ve incelenen CX-1 `app.py` içinde üretim import'u bulunmadı. CL-2 dalındaki testte import görülüyor; yayımlanacak derlemede gerçekten bulunup bulunmadığını PyInstaller envanterinden doğrulayın.
- **Lisans:** GPL-2.0-or-later.
- **Proje:** [github.com/quodlibet/mutagen](https://github.com/quodlibet/mutagen).
- **Telif:** Bileşen kaynak dosyalarındaki Mutagen katkı sahipleri (ör. Joe Wreschnig); kaynak bildirimleri korunmalıdır.
- **Tam metin:** [licenses/Mutagen-GPL-2.0-or-later.txt](licenses/Mutagen-GPL-2.0-or-later.txt), resmi upstream deposundan alınmıştır.
- **Uyum etkisi:** Mutagen Python modülü uygulamayla aynı süreçte import edilip dağıtılırsa, Arnold DW ile GPL kapsamındaki birleşik eser değerlendirmesi riski vardır. PyInstaller bootloader istisnası bu ayrı kütüphanenin GPL koşullarını kaldırmaz. Bağımlılık kullanılmıyorsa pakete almamak; gerekiyorsa uygulama lisansı, kaynak sağlama ve GPL uyumluluğu hakkında yayımdan önce hukuk incelemesi yapmak önerilir. Bu bir hukuki görüş değildir.

## Paket varlıkları

Uygulama logosu, uygulama simgesi (`logo/icon.ico`, `logo/app-logo.png`) ve tüm platform/gezinme ikonları (`logo/*.png`) Arnold DW için özgün olarak üretilmiştir; üçüncü taraf görsel varlık kullanılmaz. Platform adları ve markaları sahiplerine aittir; ikonlar yalnızca bağlantının hangi siteye ait olduğunu belirtmek için stilize edilmiş kontur yorumlarıdır.

## Derleme araçları ve ikili dosyalar

### PyInstaller ve bootloader

- **Sürüm:** Denetlenen build aracı `6.22.3`; gereksinim dosyasında sürüm sabitlenmemiştir. Uygulama çıktısında PyInstaller bootloader bulunur.
- **Lisans:** GPL-2.0-or-later, bootloader istisnasıyla. PyInstaller'ın derlenmiş bootloader'ını başka programla birleştirip dağıtma izni vardır. Runtime hook'ları ve bazı gömülü modüller Apache-2.0 olabilir; `COPYING.txt` bunları ayrıca tanımlar.
- **Proje:** [github.com/pyinstaller/pyinstaller](https://github.com/pyinstaller/pyinstaller).
- **Telif:** PyInstaller Development Team (2010–2023), Giovanni Bajo (2005–2009), önceki McMillan Enterprises çalışması (2002); ayrıntılar tam metinde.
- **Tam metin:** [licenses/PyInstaller-COPYING.txt](licenses/PyInstaller-COPYING.txt), resmi `v6.22.3` deposundan alınmıştır. Apache-2.0 runtime-hook lisansı da [licenses/Apache-2.0.txt](licenses/Apache-2.0.txt) içindedir.

### Roboto fontu (CustomTkinter varlığı)

- **Sürüm:** CustomTkinter `6.0.0` wheel'iyle gelen `Roboto-Regular.ttf` ve `Roboto-Medium.ttf`; font sürümü wheel içinde ayrıca belirtilmemiştir.
- **Lisans:** Apache-2.0.
- **Proje:** [Google Fonts Roboto](https://fonts.google.com/specimen/Roboto).
- **Telif:** Copyright © 2011 Google; font dosyalarındaki ek bildirimler saklıdır.
- **Tam metin:** [licenses/Apache-2.0.txt](licenses/Apache-2.0.txt).

### Deno

- **Version:** Deno `2.9.7`, downloaded from the official Windows x64 MSVC release asset. Archive SHA-256: `a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238`. Only `deno.exe` is included.
- **License:** MIT. Full text: [licenses/Deno-MIT.txt](licenses/Deno-MIT.txt), copied from the official Deno `v2.9.7` source tag.
- **Project/source:** [Deno v2.9.7 source](https://github.com/denoland/deno/tree/v2.9.7).

### FFmpeg

- **Version:** `tools/fetch_binaries.py` downloads the Windows x64 LGPL shared FFmpeg `n9.0.2-12-gc867e13549` asset from BtbN release tag `autobuild-2026-09-27-13-04`. Archive SHA-256: `8ee8dcffde407fe78381b8d5888a0d19dca5e20fb26cdadba78c1bbc03043e30`.
- **Included files:** `ffmpeg.exe`, `ffprobe.exe`, and the DLLs in the same release archive; `ffplay.exe` is omitted. The archive is 76,974,545 bytes and the extracted files total 156,943,360 bytes. The same-date LGPL static archive is 171,535,547 bytes, so the shared variant has the smaller installed footprint.
- **License:** LGPL version 3 or later, shared build. `ffmpeg -version` reports `--enable-version3`; its configuration contains no `--enable-gpl`, and `ffmpeg -L` prints LGPL v3 terms.
- **Project and source:** [Pinned BtbN release](https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-09-27-13-04), [BtbN build repository](https://github.com/BtbN/FFmpeg-Builds), [FFmpeg n9.0.2 source](https://github.com/FFmpeg/FFmpeg/tree/n9.0.2), and [FFmpeg license information](https://ffmpeg.org/legal.html).
- **Copyright:** FFmpeg developers and BtbN Windows build contributors. Copyright and license notices for bundled DLL components remain applicable.
- **Full license text:** [licenses/FFmpeg-LGPL-3.0.txt](licenses/FFmpeg-LGPL-3.0.txt), copied from FFmpeg n9.0.2's official `COPYING.LGPLv3` source file. The LGPL 2.1 text is included as well; the old GPL text does not describe this selected build.

## Files included with the release

The build copies this notice and the complete `licenses/` directory into the application folder. PyInstaller excludes Mutagen explicitly.
## Yayın paketine dahil edilecek bildirim dosyaları

Dağıtım gerçekten yukarıdaki bileşenleri içeriyorsa `THIRD_PARTY_NOTICES.md` ile listelenen lisans tam metinlerini kurulum klasörüne kopyalayın. Özellikle FFmpeg yapılandırması ile Mutagen'in pakete girip girmediğini son PyInstaller çıktısında doğrulamadan yayına çıkmayın. CX-1'in build betiği şu anda lisans dosyalarını kurulum klasörüne kopyalamıyor.
