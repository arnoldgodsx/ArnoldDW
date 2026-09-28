# Arnold DW

![Arnold DW](docs/images/social-preview.png)

Arnold DW, YouTube ve Instagram içeriklerini Windows bilgisayarınıza indirmenizi sağlayan masaüstü uygulamasıdır. Bağlantıyı yapıştırın, önizlemeyi görün ve indirme seçeneklerini belirleyin.

![Arnold DW ana ekranı](docs/images/baseline-home.png)

## Çalışan özellikler

- **YouTube:** Tekil video için MP4 indirme ve kaynakta bulunan en yüksek çözünürlüğe kadar kalite seçimi; MP3 için 320, 192 veya 128 kbps bit hızı seçimi.
- **Önizleme:** Video bağlantısı girildiğinde kapak, başlık, kanal ve süre bilgileri gösterilir.
- **İptal:** Devam eden YouTube ve Instagram indirmeleri iptal edilebilir.
- **Instagram gönderisi, reel veya carousel:** Gönderideki indirilebilir öğeleri önizleyip istediklerinizi seçebilirsiniz.
- **Herkese açık Instagram profili:** Gönderiler/fotoğraflar, reels/videolar ve profil fotoğrafı kategorilerinden seçim yapabilirsiniz.
- İndirme klasörü seçilebilir ve sonraki açılışlarda hatırlanır.

TikTok şu an çalışmıyor; desteklenen bir özellik olarak sunulmaz.

## Kurulum

Windows kurulum dosyasını [GitHub Releases](https://github.com/arnoldgodsx/ArnoldDW/releases/latest) sayfasından indirin. `setup.exe` dosyasını çalıştırıp kurulum adımlarını izleyin.

## Geliştirici kurulumu

Python kurulu bir Windows ortamında:

```powershell
git clone https://github.com/arnoldgodsx/ArnoldDW.git
cd ArnoldDW
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools/fetch_binaries.py
python app.py
```

`fetch_binaries.py`, derleme için gerekli ikili dosyaları indirir. Uygulamayı paketlemek için PowerShell'de `tools/build.ps1` betiğini çalıştırın.

## Proje yapısı

Uygulama `arnold_dw/main.py` üzerinden başlar; çekirdek mantık `arnold_dw/core/`, ekranlar `arnold_dw/ui/`, testler `tests/`, belgeler `docs/`, tanıtım sitesi `site/` altındadır. Mimari, katkı tarifleri ve yayınlama ayrıntıları için [geliştirici rehberine](docs/gelistirici.md) bakın.

## Üçüncü taraf lisansları

Dağıtılan paketlerin lisans ve atıfları için [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) ile yanındaki `licenses/` tam metinlerine bakın.

## Kullanıcı belgeleri

- [Kullanım kılavuzu](docs/kullanim.md)
- [Sık sorulan sorular ve sorun giderme](docs/sss.md)
- [Yasal uyarı](DISCLAIMER.md)

## English

Read the [complete English README](README.en.md) for working features, installation, developer setup, and project links.
