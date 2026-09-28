# Geliştirici rehberi

Bu rehber, depodaki mevcut mimariyi ve katkı akışını açıklar. Kullanıcı kurulumu için [kullanım rehberine](kullanim.md), bilinen sorular için [SSS'ye](sss.md) bakın.

## Mimari

| Alan | Sorumluluk |
| --- | --- |
| `arnold_dw/config.py`, `paths.py`, `log.py` | Kullanıcı ayarları, kaynak ve AppData yolları, günlükleme |
| `arnold_dw/core/` | Arayüzden bağımsız indirme, dosya adı/format seçimi, hata eşleme, HTTP ve tanılama mantığı |
| `arnold_dw/core/runtime/` | yt-dlp motor seçimi, güncellemesi ve PyInstaller içindeki ikili dosyaların bulunması |
| `arnold_dw/ui/` | Tkinter/CustomTkinter penceresi, tema, bileşenler ve ekranlar |
| `arnold_dw/ui/screens/` | Ana ekran, YouTube ve Instagram akışları; `base.py` ortak `Screen` sınıfını sağlar |
| `tests/` | Birim, entegrasyon, ağ ve isteğe bağlı dondurulmuş uygulama testleri |
| `tools/`, `packaging/` | Bağımlı ikili dosyaları alma, derleme ve kurulum yapılandırması |

Uygulama `arnold_dw/main.py` üzerinden başlar. Günlükleme başlatıldıktan ve çalışma zamanı motoru etkinleştirildikten sonra UI yüklenir. `arnold_dw.core` tkinter veya CustomTkinter içe aktarmaz. Bu sınır, UI modüllerini import kancasıyla engelleyip tüm core modüllerini yükleyen [`tests/test_core_imports.py`](../tests/test_core_imports.py) testiyle denetlenir.

Ekranlardaki ağ ve disk işleri worker thread'lerde yürür. Worker, sonucu `Screen.post(kind, ...)` ile pencerenin `ui_queue` kuyruğuna yollar. `ArnoldDW._poll_queue` mesajı Tk ana thread'inde alıp ekranda hâlâ aynı `Screen` görünüyorsa `on_<kind>(...)` işleyicisine aktarır; ekran değişmişse eski sonuç atılır. Worker doğrudan widget güncellememelidir.

## Katkı tarifleri

### Ayar alanı ekleme

1. `arnold_dw/config.py` içindeki `Settings` dataclass'ına tipli bir alan ve varsayılan değer ekleyin.
2. Alanı ihtiyaç duyan ekran/iş mantığına `app.settings` üzerinden bağlayın; kalıcılaştırmak için `save_settings` kullanın.
3. `Settings.from_dict` saklanan değeri varsayılanın türüne göre doğrular; eksik veya hatalı değer varsayılana döner.
4. Mevcut anahtarın anlamı veya biçimi değişmiyorsa `SCHEMA_VERSION` artırılmaz. Şekil/anlam değişirse `_migrate` içine geriye dönük dönüşüm ekleyin ve config testlerini güncelleyin.

### Ekran ekleme

1. `arnold_dw/ui/screens/` altında `Screen` taban sınıfından türeyen bir ekran oluşturun; `name`, `build` ve mesaj işleyicilerini (`on_<kind>`) tanımlayın.
2. Yeni ekranı `arnold_dw/ui/window.py` içindeki `SCREENS` eşlemesine ekleyin. Ana ekranda kart gerekiyorsa `ui/screens/home.py` içindeki `PLATFORMS` kaydını da ekleyin.
3. Ağ/disk işlerini `start_worker` ile başlatın, sonuçları `post` ile UI kuyruğuna verin ve ekran kapanırken işlerin temizlenmesini yönetin.

### Platform ekleme

`core/platforms` yönlendiricisi henüz bu dalda mevcut değil; mevcut yapı YouTube ve Instagram'a özgü `arnold_dw/core/youtube.py` ve `arnold_dw/core/instagram.py` modüllerini kullanıyor. Yeni akış için bunların ayrımını izleyin: saf seçim/dönüştürme mantığı core'da, kullanıcı etkileşimi ve worker yönetimi ilgili `ui/screens/` modülünde olmalı. Yönlendirici main'e geldiğinde bu bölüm gerçek arayüze göre güncellenmelidir.

### Metin ekleme / çeviri

Kullanıcıya görünen yeni metinleri `arnold_dw/i18n/tr.json` ve `arnold_dw/i18n/en.json` kataloglarına aynı anahtarla ekleyin. Anahtarları `ekran.bölüm.öğe` biçiminde adlandırın (ör. `youtube.quality.title`, `errors.private_video`); parametreleri her iki dilde aynı tutup `{name}` olarak yazın. Sayıya göre değişen metinlerde `anahtar.one` ve `anahtar.other` kullanın; çağrı `t("anahtar", count=n)` biçimindedir.

UI metnini `from arnold_dw.i18n import t` ile alıp `t("anahtar", name=value)` çağrısıyla gösterin. `t()` arayüz modüllerinde kullanılır; `arnold_dw/core/` tkinter/arayüz bağımsız kalır. Yeni hata eşlemeleri core'da i18n anahtarı döndürmemeli; kullanıcıya gösterilecek hata metnini UI katmanı çevirmelidir. Değişiklikten sonra `python tools/i18n_check.py` ile henüz taşınmamış metinleri gözden geçirin. `python tools/i18n_check.py --strict --catalog-only` katalog tutarlılığını CI için hata koduyla denetler; `--strict` tek başına henüz `t()` çağrısına taşınmamış metinleri de hata sayar. Testleri `python -m pytest tests/test_i18n.py` ile çalıştırın.

PyInstaller paketine katalogları eklemek için `ArnoldDW.spec` içindeki `datas` listesine şu satırı ekleyin: `datas += [(str(path), "arnold_dw/i18n") for path in (ROOT / "arnold_dw" / "i18n").glob("*.json")]`.

## Güncelleme ve tanılama

### yt-dlp motoru

`arnold_dw/core/runtime/ytdlp_updater.py` motoru uygulama sürümünden bağımsız günceller. PyPI'den yt-dlp wheel'ini ve gereken `yt-dlp-ejs` wheel'ini alır; boyut ve SHA-256 değerlerini doğrular, geçici `.staging-*` dizinine açar, sürümü/derlenebilirliği denetler ve tamamlanınca atomik yeniden adlandırmayla sürüm dizinine geçirir. Durum dosyası atomik yazılır. Önceki çalışan motor kurulum sırasında yerinde kalır.

Başlangıçta `EngineFinder`, güncel kullanıcı motorunu PyInstaller'ın paketli importundan önce seçer. İçe aktarma doğrulaması başarısız olursa motor bozuk olarak işaretlenir, finder kaldırılır ve sonraki kullanılabilir sürüme ya da paketlenmiş yt-dlp'ye geri dönülür. Kurulum tamamlanan motoru sonraki başlangıçta etkinleştirir.

#### Tehdit modeli

Güven zinciri, PyPI'nin TLS'ine ve `yt-dlp`/`yt-dlp-ejs` yayın hesaplarının bütünlüğüne dayanır: metadata `pypi.org`'un JSON API'sinden, wheel `files.pythonhosted.org`'dan alınır ve indirilen baytlar o JSON'daki SHA-256 ile doğrulanır - ayrı, uygulamaya gömülü bir imza yoktur. Bu nedenle PyPI hesabı veya yayın kanalı ele geçirilirse metadata ile wheel birlikte değiştirilebilir; bu risk kabul edilmiş ve hafifletilmiştir, ortadan kaldırılmamıştır (bkz. `hq/reports/CX-3-T20.md` P1). Hafifletmeler:

- **Redirect'te HTTPS/host düşürme reddi:** `requests` yönlendirmeleri sessizce takip eder; `_verify_response_origin` hem metadata (`_get_json`) hem wheel (`_download`) yanıtlarının nihai `response.url`'ünün hâlâ HTTPS ve `pypi.org`/`files.pythonhosted.org` olduğunu doğrular, aksi hâlde günceleme reddedilir. Bu, aradaki bir saldırganın yönlendirmeyi HTTP'ye ya da başka bir hosta düşürmesini engeller; PyPI'nin kendisinin ele geçirilmesine karşı koruma sağlamaz.
- **Boyut + SHA-256 doğrulaması:** indirilen wheel, PyPI JSON'unda ilan edilen boyut ve SHA-256 ile eşleşmeli; eşleşmezse kurulum iptal edilir ve önceki motor yerinde kalır.
- **`state.json` ↔ `engine.json` tutarlılığı:** bir motor dizini yalnızca kendi `engine.json` manifestindeki `version` alanı dizin adıyla eşleşiyorsa "kurulu" sayılır (`installed_versions`). Yarım kalan bir kurulum veya yerel kurcalama bu eşleşmeyi bozar; böyle bir dizin asla etkinleştirilmez, geri dönüş hedefi olarak sunulmaz ve bir sonraki `_prune` çağrısında silinir.
- **`remote_components=["ejs:github"]` kararı:** yt-dlp'nin YouTube "n"/imza çözücü betikleri normalde uygulamayla birlikte gelen `yt-dlp-ejs` paketinden okunur (ağ erişimi gerekmez). Bu ayar yalnızca yerel `yt-dlp-ejs` sürümü aktif motorun beklediği sürümle uyuşmadığında (ör. motor güncellemesinden hemen sonra, ejs paketi henüz gelmemişse) devreye girip yt-dlp'nin kendi GitHub release akışından çekmesine izin verir; yt-dlp bu betikleri kendi kodunda gömülü hash'lerle doğrular. Bu, ekstra bir ağ yolu açar ama korumasız değildir; yalnızca uyumsuzluk durumunda tetiklenir ve içerik hash ile doğrulanır.

Bu katman, aynı kullanıcı hesabıyla çalışan yerel bir sürece karşı tam koruma sağlamaz (dosya izinleri/ACL doğrulaması yapılmaz); tehdit modeli ağ üzerinden gelen (MITM, redirect, ele geçirilmiş yayın) saldırılara odaklıdır. Ayrıntılı bulgular ve önerilen ileri adımlar (manifest imzalama, ACL doğrulaması) için `hq/reports/CX-3-T20.md`.

### Uygulama güncellemesi

`arnold_dw/core/appupdate.py` GitHub Releases `latest.json` manifestini okur. Daha yeni sürümün kurulum dosyası URL, pozitif boyut ve SHA-256 ile doğrulanır; indirme boyutu sınırlandırılır, hash eşleşince `.part` dosyası atomik olarak son adına taşınır. `launch_installer` Inno Setup'ı çalıştırır. Bu modülün check/download/launch işlevleri şu an UI akışına bağlanmamıştır. Manifest üretimini `tools/make_manifest.py`, etiketli yayın akışını `.github/workflows/release.yml` yürütür.

### Tanılama paketi

`arnold_dw/core/diagnostics.py` çağıranın verdiği hedef dizinde tarihli ZIP oluşturur: sistem/sürüm bilgisi, ayar JSON'u ve en yeni günlüklerden toplam en fazla 5 MB. Kullanıcı adı, URL sorgu değerleri ve tanınan çerez/yetkilendirme/token/parola benzeri değerler pakete yazılmadan maskelenir. Bu modül şu an UI akışına bağlanmamıştır. Maskeleme yaygın biçimleri hedefler; kullanıcı paketi paylaşmadan önce içeriğini incelemelidir.

## Geliştirme ve test

Depo kökünde Windows sanal ortamı oluşturup `requirements.txt` ve `requirements-dev.txt` bağımlılıklarını kurun. Kaynak çalıştırma için `python app.py`; lint için `python -m ruff check .`; varsayılan test paketi için `python -m pytest` kullanın.

`tests/conftest.py`, `network` işaretli testleri varsayılan olarak atlar. Ağ erişimi gerektiren testleri `python -m pytest --network` ile çalıştırın. PyInstaller ile gerçek dondurulmuş motor güncelleme testleri ek olarak `ARNOLD_DW_FROZEN_TEST=1` ister; bu testler yavaş ve internet bağımlıdır (ör. PowerShell: `$env:ARNOLD_DW_FROZEN_TEST='1'; python -m pytest --network tests/test_runtime_frozen.py`).

## Sürüm yayınlama

Sürüm numarasını `arnold_dw/__init__.py` içindeki `__version__` ile uyumlu tutun. `v<version>` etiketi `.github/workflows/release.yml` akışını başlatır; lint ve testlerden sonra Windows kurulum ve taşınabilir ZIP çıktıları üretilir. Akış tag ile uygulama sürümünün eşleşmesini zorunlu tutar, GitHub Release'e dosyaları ekler ve kurulum URL'si, boyutu, SHA-256'sı, sürüm/tarih/notlar içeren `latest.json` manifestini yayımlar.
