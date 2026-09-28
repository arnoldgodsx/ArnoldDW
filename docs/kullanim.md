# Kullanım kılavuzu

## Uygulamayı açma

Arnold DW'yi Başlat menüsünden veya kurulum sırasında oluşturulan kısayoldan açın. Ana ekranda YouTube ve Instagram ekranlarından birini seçin. Ana ekrandaki TikTok kartı şu an çalışır bir indirme akışı sunmaz.

## YouTube videosu indirme

1. YouTube'daki tekil video bağlantısını YouTube ekranındaki alana yapıştırın.
2. Uygulama bağlantıyı çözümlerken önizlemenin yüklenmesini bekleyin. Kapak görseli, başlık, kanal ve süre bilgileri görünür.
3. **MP4** veya **MP3** biçimini seçin. MP4'te kalite menüsü, videonun sağladığı çözünürlüklerle sınırlıdır; listede olmayan bir çözünürlük seçilemez. MP3'te 320, 192 veya 128 kbps seçenekleri bulunur.
4. **Gözat** düğmesiyle mevcut bir indirme klasörü seçebilirsiniz. Varsayılan klasör `İndirilenler\Arnold DW` konumudur. Seçtiğiniz klasör sonraki açılışlarda hatırlanır.
5. **İndir** düğmesine basın. İndirme sırasında ilerleme, hız ve tahmini kalan süre gösterilir. Aynı düğme üzerinden işlemi iptal edebilirsiniz.

Dosya adı, video başlığı ve video kimliğinden oluşturulur. MP4 çıktısı MP4 kapsayıcısında birleştirilir; MP3 seçimi seçilen bit hızını kullanır.

## Instagram içeriği indirme

1. Bir gönderi/reel bağlantısı veya herkese açık profil bağlantısı ya da kullanıcı adı girin.
2. Önizleme geldikten sonra gönderideki tek tek medya öğelerini seçin. Carousel içindeki fotoğraf ve videolardan yalnızca işaretledikleriniz indirilir.
3. Profil için **Gönderiler / Fotoğraflar**, **Reels / Videolar** ve **Profil Fotoğrafı** kategorilerinden istediklerinizi işaretleyin.
4. **İndir** düğmesine basın; işlem sırasında aynı düğme indirmeyi iptal eder.

Uygulama Instagram profil öğelerini seçili indirme klasörüne yazar. Aynı adlı dosya zaten varsa üzerine yazmak yerine o öğeyi atlar. Gizli profillerde yalnızca profil fotoğrafı seçilebilir. Instagram erişim sınırları, içeriğin kaldırılmış olması veya bağlantı hataları indirmeyi engelleyebilir.

## İndirme klasörünü değiştirme

YouTube ekranındaki **Kayıt Konumu** alanı geçerli klasörü gösterir. **Gözat** düğmesine basıp var olan bir klasör seçin. Bu seçim YouTube ve Instagram indirmelerinde kullanılır ve uygulama ayarlarında saklanır.

## YouTube video ve gömme seçeneklerini değiştirme

Ana ekrandaki dişli (⚙) düğmesiyle **Ayarlar** ekranını açın. **İndirme** bölümünde video modunu seçebilirsiniz:

- **Maksimum uyumluluk (H.264):** H.264 görüntü ve AAC ses kullanır; geniş oynatıcı ve telefon uyumluluğu sağlar. YouTube bu modda en fazla 1080p sunar.
- **En yüksek kalite:** Kaynağın en iyi akışlarını (varsa VP9 veya AV1) 4K'ya kadar kullanır. Bazı eski oynatıcılar bu dosyaları açamayabilir.

Başlık, sanatçı ve bölüm bilgilerinin dosyaya gömülmesini ve kapak görselinin eklenmesini açıp kapatabilirsiniz. Bu seçenekler ffmpeg gerektirir; MP4'e kapak eklemek için ayrıca ffprobe gerekir. Gerekli araçlardan biri yoksa Ayarlar ekranında bildirilir.

## İndirme motorunu güncelleme

Ana ekrandaki dişli düğmesinden **Ayarlar** ekranını açın. **İndirme motoru** bölümü yüklü yt-dlp sürümünü ve uygulamayla gelip gelmediğini gösterir. **Güncellemeleri denetle** ile yeni sürüm arayın. Yeni sürüm bulunursa yüklemeyi başlatmak için **İndir ve kur** seçeneğini onaylayın; mevcut sürümü korumak için **Vazgeç**'i seçin. İndirme sırasında güncellemeyi iptal edebilirsiniz.

**Kararlı** kanalı normal sürümleri, **Nightly** kanalı erken düzeltmeleri sunar. Nightly YouTube değişikliklerini birkaç gün önce çözebilir; sorun çıkarsa uygulama önceki motora dönebilir. Günde bir kez otomatik denetimi açabilirsiniz; güncelleme yalnızca onayınızla kurulur. Kurulumdan sonra yeni motoru etkinleştirmek için **Şimdi yeniden başlat**'ı seçin. Etkin indirmeler varsa yeniden başlatma bunları iptal edeceğinden uygulama onay ister.

Ayarlar ekranındaki **Yardımcı araçlar** durumu JavaScript çalışma zamanının, ffmpeg'in ve ffprobe'un bulunup bulunmadığını gösterir. Tanılama kayıtlarını görmek için **Hakkında** bölümünde **Log klasörünü aç** düğmesini kullanın.

## English

See the [English user guide](en/usage.md).
