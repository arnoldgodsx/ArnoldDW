# Sürüm yayınlama kontrol listesi

Bu liste GitHub Actions'taki `.github/workflows/release.yml` akışına göre hazırlanmıştır. Akış, `v*` etiketini izler; sürüm ve etiket aynı değilse yayını durdurur.

## Yayın öncesi

- [ ] `arnold_dw/__init__.py` içindeki `__version__` değerini yayınlanacak kararlı sürüme yükseltin (ör. `1.0.1`). Geliştirme son ekini (`.dev0`) kaldırın.
- [ ] `CHANGELOG.md` içindeki `[Unreleased]` değişikliklerini yeni sürüm başlığı ve yayın tarihi altında toplayın; sonraki çalışmalar için boş bir `[Unreleased]` bölümü bırakın.
- [ ] Değişiklikleri gözden geçirin ve CI'nin lint ile test adımlarının başarılı olduğunu doğrulayın.
- [ ] Etiketi sürümle birebir aynı oluşturun: `vX.Y.Z` = `__version__` (ör. `v1.0.1`). Bu etiketi göndermek `release.yml` akışını başlatır.

## GitHub Release çıktıları

Windows akışı uygulamayı derler ve şu dosyaları üretip GitHub Release'e ekler:

- `ArnoldDW-X.Y.Z-setup.exe`: Inno Setup kurucusu.
- `latest.json`: kurulum dosyasının sürümünü, indirme adresini, boyutunu ve SHA-256 özetini içeren güncelleme manifesti.

Release notları eşleşen `CHANGELOG.md` sürüm bölümünden alınır. `latest.json` Ed25519 ile imzalanır ve yalnızca `ARNOLD_DW_RELEASE_KEY` deposu sırrı tanımlıysa yayınlanır; sır yoksa akış uyarı verip manifestsiz yayın yapar.

Akış, yayından önce `tools/installer_smoke.ps1` ile kurucuyu temiz runner'da sessizce kurar, kısayolları ve Uygulamalar girişini denetler, uygulamayı başlatır ve açıkken kaldırır; herhangi bir adım başarısız olursa yayın yapılmaz.

## Temiz Windows kurulum duman testi

Sanal makine veya Arnold DW'nin önceden kurulmadığı temiz bir Windows hesabı kullanın.

1. [ ] GitHub Release sayfasında sürüm etiketi, notlar ve kurulum dosyasının (gerekirse `latest.json`) bulunduğunu, dosya adındaki sürümün doğru olduğunu kontrol edin.
2. [ ] `setup.exe` dosyasını indirin. Windows SmartScreen, kod imzalama sertifikası olmadığı için “Windows bilgisayarınızı korudu” / “Bilinmeyen yayıncı” uyarısı gösterebilir. Yayınlanan dosyanın kaynağını doğruladıktan sonra **Daha fazla bilgi → Yine de çalıştır** ile devam edin; bu uyarıyı imzalı uygulama gibi sunmayın.
3. [ ] Kurulumu tamamlayın, Başlat menüsü veya masaüstü kısayolundan uygulamayı açın ve ana pencerenin hatasız geldiğini doğrulayın.
4. [ ] YouTube ekranını açın; kısa ve herkese açık bir videonun önizlemesini yükleyin, MP4 veya MP3 indirmesini başlatıp tamamlandığını ve dosyanın seçili klasörde açılabildiğini doğrulayın.
5. [ ] Instagram ekranında herkese açık bir gönderi önizlemesini yükleyin ve seçilebilir medya öğesinin indirme akışını doğrulayın. Platform erişim sınırları nedeniyle bu adımda kullanılabilir, herkese açık bir test gönderisi seçin.
6. [ ] Uygulamayı kapatıp yeniden açın; seçilen indirme klasörünün korunduğunu kontrol edin. Kurulum kısayolunun ve kaldırma girişinin Windows uygulama listesinde bulunduğunu doğrulayın.

## Geri alma

1. [ ] Sorunlu GitHub Release'i düzenleyip **Draft** durumuna alın; böylece yeni kararlı yayın olarak sunulmasını durdurun. Gerekirse hatalı etiketi silip düzeltilmiş sürüm etiketiyle yeniden yayınlayın.
2. [ ] `latest.json` güncelleme akışında kullanılacaksa, manifestin `version`, kurulum URL'si, `size` ve `sha256` değerlerini bir önceki çalışan sürümün gerçek kurulum dosyasıyla eşleştirin. Manifesti önceki sürümün `latest.json` dosyasıyla değiştirip yayınlayın; eski kurulum dosyasının Release indirme adresinde erişilebilir kaldığını doğrulayın.
3. [ ] Manifest için dijital imza şartı T22 ile eklendikten sonra, geri alınan manifesti de o akışın imzalama yöntemiyle imzalayın ve temiz ortamda doğrulayın.
4. [ ] Release sayfasında önceki çalışan sürümün en güncel kararlı yayın olarak göründüğünü ve `latest.json` indirme adresinin doğru manifesti döndürdüğünü kontrol edin.

Not: Uygulamadaki güncelleme kontrolü ve indirme modülü şu an arayüze bağlı değildir; manifesti geri almak tek başına kurulu istemcilerde kullanıcıya görünen bir geri alma düğmesi sağlamaz.
