# Changelog

Bu dosya [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) biçimini izler. Sürüm numaraları [Semantic Versioning](https://semver.org/) ile uyumludur.

## [Unreleased]

## [1.0.0] - 2026-10-12

İlk herkese açık kararlı sürüm.

### Added
- **Kurulum sihirbazı ve kaldırıcı:** Türkçe/İngilizce kurulum sihirbazı (dil seçimi, kullanım koşulları sayfası, klasör seçimi, yalnızca kendim için / tüm kullanıcılar için kurulum, isteğe bağlı masaüstü kısayolu, kurulum sonunda başlatma). Başlat menüsünde "Arnold DW'yi kaldır" kısayolu ve Uygulamalar listesinde kaldırma girişi. Kaldırıcı açık uygulamayı kapatır, ayar/geçmiş/günlük verilerini silmeyi sorar ve indirilen dosyalara dokunmaz.
- Güncelleme kurulumu önceki sürümün çalışma dosyalarını temizler, dil/klasör/kısayol tercihlerini hatırlar.
- CI her push'ta kurulum dosyasını derler, sessiz kurulum → başlatma → kaldırma testini çalıştırır (`tools/installer_smoke.ps1`).
- **İndirme kuyruğu ve "İndirmeler" ekranı:** link yapıştırıp "İndir"e basınca iş kuyruğa girer, ekran hemen yeni link için hazır olur. Aynı anda en fazla 2 indirme; ilerleme alttaki şeritte ve İndirmeler sekmesinde. Tamamlananlar için Aç / Klasörde göster / Tekrar dene; geçmiş uygulama kapanıp açılınca korunur.
- Alt gezinme çubuğu (Ana Sayfa · İndirmeler, aktif indirme rozetiyle).
- **Ayarlar ekranı** (ana ekranda ⚙): kayıt klasörü, video modu (Maksimum uyumluluk H.264 / En yüksek kalite), başlık-sanatçı-bölüm bilgisi ve kapak gömme, indirme motoru (yt-dlp) güncellemesi (denetle → indir → yeniden başlat), güncelleme kanalı, günlük otomatik denetim, yardımcı araç durumu.
- Motor güncellemesi olduğunda ana ekranda göze batmayan bildirim; kurulum her zaman kullanıcı onayıyla.
- Instagram herkese açık profillerinde toplu indirme için isteğe bağlı "tarayıcı oturumumu kullan" seçeneği (Firefox/Edge/Chrome/Brave; açık onayla, çerezler kaydedilmez).
- Aynı video farklı kalitede tekrar indirilebilir (dosya adında kalite); zaten indirilmiş dosya tespit edilir.
- İndirme sürerken pencere kapatılırsa onay sorulur; uygulama ikinci kez açılmaz, mevcut pencere öne gelir.
- Tanıtım sitesinde Türkçe ve İngilizce dil seçeneği; İngilizce README ve kullanıcı belgeleri; geliştirici kılavuzu.

### Changed
- YouTube'da tüm kaliteler (4K'ya kadar) yeniden listeleniyor: YouTube'un JavaScript doğrulaması için Deno çalışma zamanı pakete eklendi.
- MP4'ler varsayılan olarak her oynatıcıda sesli/görüntülü açılan H.264 + AAC olarak indirilir.
- Dikey videolarda (Shorts vb.) kalite sınırı kısa kenara göre uygulanır; seçilen kalite aşılmaz.
- Instagram motoru yeniden yazıldı: reel/video yt-dlp ile, fotoğraf/carousel Instaloader ile; erişim sınırında art arda deneme yapılmaz, bekleme süresi bildirilir.
- ffmpeg, LGPL lisanslı derlemeyle (ffmpeg + ffprobe) değiştirildi.
- Uygulama, platform ve gezinme ikonları özgün çizimlerle yenilendi.
- Tanıtım sitesi paylaşım kartları, küçük ekran düzeni; lisans, kullanım ve sorun giderme belgeleri.

### Fixed
- Her gece çalışan platform kontrolü (nightly) eski önbellek anahtarı yüzünden her gün başarısız oluyordu; düzeltildi.
- Hızlı link değişiminde eski videonun önizlemesinin yeni linkin yerine geçmesi.
- İptal edilen/başarısız indirmelerin yarım dosya bırakması; Instagram'da yarım dosyanın sonraki denemeyi engellemesi.
- "İşleniyor" durumunun erken başlayıp İptal'i kapatması.
- Metni değiştirmeyen tuşların (ok tuşları, Ctrl+C) önizlemeyi silmesi.
- İkinci ziyarette açılır menünün dışarı tıklayınca kapanmaması.
- Instagram erişim sınırı hatalarının yanlışlıkla "giriş gerekli" diye gösterilmesi.
- Toplam boyutu bilinmeyen indirmelerde ilerlemenin %0'da takılı görünmesi.

### Removed
- Instagram'da arama motoru botu kimliğine bürünme ve sabit GraphQL sorgusu.
- Tıklanınca hiçbir şey yapmayan TikTok kartı (TikTok ekranı hazır olana kadar gizli).

### Security
- İndirme motoru güncellemeleri PyPI'den yalnızca HTTPS ile, SHA-256 doğrulamalı, kademeli kurulum ve otomatik geri dönüşle yapılır.
- Uygulama güncelleme manifesti Ed25519 ile imzalanır; imzasız/kurcalanmış manifest, HTTP ya da izinsiz adres reddedilir.
- Sınırlı HTTP yanıt boyutları; tanılama paketinde çerez, token ve hesap adları maskelenir.
- Üçüncü taraf görsel varlık kalmadı; GPL lisanslı Python kütüphanesi kullanılmaz.

### Performance
- Paket UPX olmadan derlenir (daha hızlı açılış, daha az antivirüs yanlış alarmı); test/derleme araçları ve kullanılmayan ağır modüller pakete girmez.
- Kurucu LZMA2/ultra64 ile sıkıştırılır.

### Altyapı (henüz arayüzde değil)
- TikTok (filigransız video, ses, fotoğraf slaytı), X, Reddit, SoundCloud, Twitch ve Dailymotion indirme motorları ile YouTube oynatma listesi listeleme — ekranları henüz yok.
- Uygulama güncelleme, tanılama paketi ve Windows bildirimi modülleri — arayüze bağlı değil.
- Türkçe/İngilizce arayüz metin katalogları — arayüzde dil seçimi henüz yok.

## [0.2.0] - 2026-07-29 (iç önizleme, yayınlanmadı)

### Added
- Instagram gönderi ve herkese açık profil indirme ekranı.
- Platform ana ekranı.

## [0.1.0] - 2026-07-29 (iç önizleme, yayınlanmadı)

### Added
- YouTube video ve ses indirme uygulaması.
