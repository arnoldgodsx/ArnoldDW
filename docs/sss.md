# Sık sorulan sorular ve sorun giderme

## Video sessiz açılıyor

MP4 indirmede uygulama mümkün olduğunda AAC ses akışını tercih edip videoyla MP4 içinde birleştirir; kaynakta uygun ses yoksa mevcut akışa düşebilir. Dosyayı başka bir oynatıcıda deneyin ve indirmeyi tekrar başlatın. Her kaynakta ses parçası bulunması garanti değildir.

## YouTube hatası — motoru güncelle

YouTube tarafındaki değişiklikler indirme motorunun bağlantıyı çözümlemesini etkileyebilir. Ana ekrandaki dişli düğmesinden **Ayarlar**'ı açıp **İndirme motoru** bölümünde **Güncellemeleri denetle**'yi seçin. Yeni yt-dlp sürümü bulunursa **İndir ve kur**'u seçip kurulumdan sonra uygulamayı yeniden başlatın. Erken düzeltmeler için **Nightly** kanalını seçebilirsiniz; sorun çıkarsa uygulama önceki motora dönebilir. Hata sürerse [GitHub Issues](https://github.com/arnoldgodsx/ArnoldDW/issues) sayfasına uygulama sürümü ve hata adımlarıyla bildirim bırakın. Parola, çerez veya özel bağlantı paylaşmayın.

## Instagram çok fazla istek bildiriyor

Instagram geçici olarak istekleri sınırlamış olabilir. Bir süre bekleyip yeniden deneyin; art arda çok sayıda profil veya gönderi isteği göndermeyin. Erişim hatası sürerse daha sonra tekrar deneyin.

## Gizli hesaptan içerik indirebilir miyim?

Hayır. Gizli profil için uygulama yalnızca profil fotoğrafı seçeneğini sunar. Gizli gönderi ve videolar indirilemez.

## Antivirüs kurulum dosyasını tehdit olarak algılıyor

PyInstaller ile paketlenen uygulamalar bazı antivirüslerde yanlış pozitif uyarı alabilir. Bu uyarıyı yok saymadan önce kurulum dosyasını yalnızca resmi [GitHub Releases](https://github.com/arnoldgodsx/ArnoldDW/releases/latest) sayfasından indirdiğinizi doğrulayın. Dosyayı antivirüs sağlayıcısının inceleme kanalına bildirebilirsiniz.

## İndirme klasörünü veya dosya adını nasıl değiştiririm?

YouTube ekranında **Gözat** ile mevcut bir klasör seçin. Uygulama seçimi hatırlar. YouTube dosya adı video başlığı ve kimliğine göre oluşturulur; Instagram dosyaları da kullanıcı adı, gönderi kısa kodu ve öğe sırasını içerir.

## Video kalitesi, kapak veya bilgi gömme seçeneklerini nereden değiştiririm?

Ana ekrandaki dişli düğmesiyle **Ayarlar** ekranını açın. **İndirme** bölümünde **Maksimum uyumluluk (H.264)** veya **En yüksek kalite** modunu seçebilir, bilgi ve kapak görseli gömmeyi açıp kapatabilirsiniz. Bu seçenekler ffmpeg gerektirir; MP4'e kapak eklemek için ffprobe da gerekir. Gerekli araç yoksa Ayarlar ekranı bunu bildirir.

## YouTube indirme motorunu nasıl güncellerim?

Ana ekrandaki dişli düğmesiyle **Ayarlar** ekranını açıp **İndirme motoru** bölümünde **Güncellemeleri denetle**'yi seçin. Sürüm bulunursa **İndir ve kur** ile onaylayın. İsterseniz **Nightly** kanalında erken düzeltmeleri alabilirsiniz. Kurulum tamamlanınca uygulamayı yeniden başlatıp yeni motoru etkinleştirin. Günlük otomatik denetim yalnızca haber verir; kurulum yine onay ister.

## English

See the [English FAQ and troubleshooting guide](en/faq.md).

## Arnold DW'yi nasıl kaldırırım?

**Ayarlar → Uygulamalar → Yüklü uygulamalar** (veya **Denetim Masası → Programlar ve Özellikler**) içinde **Arnold DW**'yi bulup **Kaldır**'ı seçin. Başlat menüsündeki Arnold DW klasöründe bulunan **Arnold DW'yi kaldır** kısayolunu da kullanabilirsiniz. Uygulama açıksa kaldırıcı onu kapatmayı önerir. Ardından `%APPDATA%\Arnold DW` içindeki ayarlar, indirme geçmişi, günlükler ve motor güncellemelerinin silinip silinmeyeceğini sorar; yeniden kurulumda kullanmak için **Hayır** deyin. İndirdiğiniz dosyalar hiçbir zaman silinmez.

Komut satırından kaldırmak için kurulum klasöründe `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES` çalıştırın; kullanıcı verileri korunur.
