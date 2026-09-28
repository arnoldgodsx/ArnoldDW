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

### Icons8 görseli

- **Sürüm/aralık:** Uygulama `logo/icons8-fire-48.png` ve `logo/icons8-fire-96.png` dosyalarını, site ise 96 px logonun kopyasını ve baseline ekran görüntüsünü kullanır. İndirme kaydı/sürümü repoda yoktur.
- **Lisans:** Icons8'in ücretsiz varlık kullanım koşulları; masaüstü uygulamalarında About bölümünde Icons8 bağlantısı istenir. Site footer'ına Icons8 atıf bağlantısı eklendi. Uygulama kodunda bu görev kapsamındaki izinli dosyalar arasında About alanı yoktur.
- **Proje/koşullar:** [Icons8 lisans koşulları](https://icons8.com/license).
- **Telif:** İndirilen ikonun sayfası ve eser sahibi depoda kayıtlı değildir; ilgili asset sayfasındaki atıf esas alınmalıdır. Diğer `logo/*.png` platform simgelerinin kaynağı da depoda belirtilmemiştir ve ayrıca doğrulanmalıdır.
- **Tam metin:** Bu bir yazılım lisansı değil, çevrimiçi kullanım koşullarıdır; [Icons8 lisans sayfası](https://icons8.com/license) esas alınır. Site footer'ında atıf bağlantısı yer alır. Uygulamanın About alanı bu görevde düzenlenemedi; AG-1 özgün logo çalışması yayıma alınırken uygulama simgesini ve site logosunu da Icons8 varlığından çıkarın ya da masaüstü uygulamasında gereken atfı sağlayın.

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

### FFmpeg

- **Sürüm:** CX-1'in `tools/fetch_binaries.py` dosyası Gyan.dev `ffmpeg-9.0.2-essentials_build.zip` arşivini indirir. Sabit arşiv SHA-256: `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`; FFmpeg ikili SHA-256: `3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec`.
- **Lisans:** Gyan.dev bu statik Essentials derlemesini GPLv3 olarak tanımlar. Bu, genel FFmpeg varsayılan lisansından farklıdır: FFmpeg'in kendisi çoğunlukla LGPL olsa da `--enable-gpl` bileşenleri veya GPL codec kütüphaneleri birleşik FFmpeg ikilisini GPL kapsamına sokar.
- **Proje/kaynak:** [Gyan.dev FFmpeg Builds](https://www.gyan.dev/ffmpeg/builds/), [FFmpeg kaynak commit'i 946fcce07b](https://github.com/FFmpeg/FFmpeg/commit/946fcce07b), [FFmpeg lisans açıklaması](https://ffmpeg.org/legal.html).
- **Telif:** FFmpeg geliştiricileri; Windows build/dağıtımı Gyan Doshi tarafından sağlanır. Bileşen kaynaklarındaki telif bildirimleri geçerlidir.
- **Tam metin:** [licenses/FFmpeg-GPLv3.txt](licenses/FFmpeg-GPLv3.txt), FFmpeg kaynak commit'inden kopyalanmıştır.
- **Denetlenen derleme ayarları:** `--enable-gpl --enable-version3 --enable-static`; ayrıca `--enable-cairo`, `--enable-fontconfig`, `--enable-gnutls`, `--enable-gmp`, `--enable-libsrt`, `--enable-libssh`, `--enable-libzmq`, `--enable-libwebp`, `--enable-libx264`, `--enable-libx265`, `--enable-libxvid`, `--enable-libaom`, `--enable-libopenjpeg`, `--enable-libvpx`, `--enable-libass`, `--enable-libfreetype`, `--enable-libfribidi`, `--enable-libharfbuzz`, `--enable-libvidstab`, `--enable-libvmaf`, `--enable-libzimg`, `--enable-libgme`, `--enable-libopenmpt`, `--enable-libmp3lame`, `--enable-libtheora`, `--enable-libvo-amrwbenc`, `--enable-libgsm`, `--enable-libopencore-amrnb`, `--enable-libopus`, `--enable-libspeex`, `--enable-libvorbis` ve `--enable-librubberband`.
- **Derleme telifleri:** `ffmpeg -version` çıktısı `Copyright (c) 2000-2026 the FFmpeg developers` ve Gyan.dev derlemesini doğruladı. Gyan Essentials, yukarıdaki statik kodlayıcı/kütüphanelerle tek bir GPLv3 FFmpeg ikilisi oluşturur. Bunların tam sürümleri ve lisansları binary fetch betiğinde kaydedilmemiştir; FFmpeg kaynak commit'i tek başına dış kitaplıkların karşılık gelen kaynaklarını veya Gyan yapılandırma betiklerini içerdiğini kanıtlamaz.
- **GPL/source durumu ve öneri:** Kurulum paketinde bu GPLv3 statik ikiliği dağıtacaksak ikiliyle eşleşen FFmpeg ve dahil edilmiş bağımlılıkların karşılık gelen kaynak kodu, build/configure bilgisi ve ilgili lisans bildirimleri erişilebilir tutulmalıdır. Mevcut `fetch_binaries.py` bunları indirmiyor veya yayımlamıyor. Basit ve düşük yük getiren yol, `--enable-gpl` olmadan oluşturulmuş, yapılandırması ve lisansları doğrulanmış LGPL derlemesine geçmektir. Gyan sayfasındaki mevcut release Essentials derlemesi LGPL değildir. Nihai seçim ve kaynak sunumu YN-0 tarafından onaylanmalıdır; bu metin hukuki görüş değildir.

## Yayın paketine dahil edilecek bildirim dosyaları

Dağıtım gerçekten yukarıdaki bileşenleri içeriyorsa `THIRD_PARTY_NOTICES.md` ile listelenen lisans tam metinlerini kurulum klasörüne kopyalayın. Özellikle FFmpeg yapılandırması ile Mutagen'in pakete girip girmediğini son PyInstaller çıktısında doğrulamadan yayına çıkmayın. CX-1'in build betiği şu anda lisans dosyalarını kurulum klasörüne kopyalamıyor.
