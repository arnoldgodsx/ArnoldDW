# Changelog

Bu dosya [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) biçimini izler. Sürüm numaraları [Semantic Versioning](https://semver.org/) ile uyumludur.

## [Unreleased]

### Added
- Tanıtım sitesinde Türkçe ve İngilizce dil seçeneği.
- Uygulamanın kaynak koduna katkı vermek ve yerel geliştirme ortamı kurmak için geliştirici kılavuzu.

### Changed
- Tanıtım sitesi artık paylaşım kartlarında başlık, açıklama ve sosyal önizleme görseli sunuyor; seçilen dil sayfa dilini ve açıklamayı da güncelliyor.
- Uygulama, platform ve gezinme ikonları özgün çizimlerle yenilendi.
- Tanıtım sitesi küçük ekranlara ve taşma kontrolüne göre düzenlendi.
- Lisans ve yasal bildirimler, kullanım ve sorun giderme belgeleri tamamlandı.

### Fixed
- Instagram erişim sınırı hataları artık yanlış biçimde “giriş gerekli” olarak açıklanmıyor.

### Security
- Sınırlı HTTP yanıt boyutları ve başarısız/iptal edilmiş indirmelerde geçici dosya temizliği eklendi.
- Üçüncü taraf ikonlar ve özgün olmayan uygulama görselleri kaldırıldı; depoda lisans koşulları açıklanmayan görsel varlık bırakılmadı.
- Güncelleme paketi indirilirken boyut ve SHA-256 denetleniyor. Güncelleme manifesti imzası henüz doğrulanmıyor; imzalı güncelleme desteği T22 merge edilince bu başlığa eklenecek.

### Altyapı (henüz arayüzde değil)
- YouTube oynatma listeleri, TikTok ve genel site indirmeleri için motor/ayrıştırıcı altyapısı eklendi. Bunlar uygulamada kullanılabilir indirme akışları olarak sunulmuyor.
- Uygulama güncelleme, tanılama paketi oluşturma ve Windows bildirim modülleri eklendi; arayüze bağlı değiller.
- `yt-dlp` motorunu güncelleme/geri alma ve ffmpeg ile JavaScript çalışma zamanı bulma altyapısı eklendi.
- Türkçe/İngilizce uygulama metin katalogları eklendi; uygulama arayüzünde dil seçimi henüz yok.

## [1.1] - 2026-07-29

### Added
- Instagram gönderi ve herkese açık profil indirme ekranı.
- Platform ana ekranı.

## [1.0] - 2026-07-29

### Added
- YouTube video ve ses indirme uygulaması.
