const copy = {
  tr: {
    description:"Arnold DW, YouTube ve Instagram içeriklerini Windows bilgisayarınızda yönetmenize yardımcı olan masaüstü uygulamasıdır.",
    ogDescription:"YouTube videolarını ve Instagram içeriklerini önizle, seç ve Windows bilgisayarına indir.",
    skip:"İçeriğe geç", navLabel:"Ana gezinme", navFeatures:"Özellikler", navHow:"Nasıl çalışır", navFaq:"SSS",
    eyebrow:"WINDOWS İÇİN MASAÜSTÜ UYGULAMASI", heroTitle:'Medyan,<br><span>senin kontrolünde.</span>', heroLead:"YouTube videolarını ve Instagram içeriklerini önizle, seç ve bilgisayarına indir. Sade, hızlı, senin kontrolünde.", download:"Windows için indir", explore:"Özellikleri keşfet", heroNote:"Windows masaüstü uygulaması", shotCaption:"Önizle. Seç. İndir.", heroFoot:"İndirme kararını sen verirsin.",
    featuresEyebrow:"DAHA AZ UĞRAŞ, DAHA ÇOK KONTROL", featuresTitle:'İhtiyacın olan her şey.<br><span>Fazlası değil.</span>', youtubeTitle:"YouTube, tercihlerinle", youtubeText:"Videonu önce gör. MP4 için uygun görüntü kalitesini, MP3 için bit hızını seç. İndirme sırasında ilerlemeyi izle veya işlemi iptal et.", previewChip:"Önizleme", instagramTitle:"Instagram'da seçerek indir", instagramText:"Gönderi ve carousel öğelerini tek tek seç. Herkese açık profillerde gönderiler, reels ve profil fotoğrafı kategorilerinden kararını ver.", controlTitle:"Kayıt yeri sende", controlText:"İndirmelerini istediğin klasöre kaydet. Seçimin bir sonraki açılışında da hatırlansın.",
    howEyebrow:"ÜÇ ADIMDA", howTitle:"Linkten dosyana.", step1Title:"Bağlantıyı ekle", step1Text:"YouTube videosu veya Instagram gönderi/profil bağlantısını yapıştır.", step2Title:"Önizle ve seç", step2Text:"İçeriği kontrol et, kaliteyi ya da indireceğin öğeleri belirle.", step3Title:"İndir", step3Text:"İndirmeyi başlat, ilerlemeyi takip et ve istersen iptal et.", faqEyebrow:"MERAK EDİLENLER", faqTitle:"Kısa cevaplar.", faq1q:"Hangi platformlar destekleniyor?", faq1a:"Şu an YouTube tekil videoları ve Instagram gönderileri ile herkese açık profiller destekleniyor. TikTok şu an çalışmıyor.", faq2q:"İndirdiklerim nereye kaydediliyor?", faq2a:"Varsayılan konum İndirilenler klasöründeki Arnold DW klasörüdür. Uygulamada başka bir klasör seçebilirsin; seçimin hatırlanır.", faq3q:"Instagram'da gizli profili indirebilir miyim?", faq3a:"Hayır. Gizli profillerde yalnızca profil fotoğrafı indirilebilir.", faq4q:"İndirme ücretsiz mi?", faq4a:"Uygulama GitHub Releases üzerinden dağıtılır. Güncel sürüm ve dağıtım koşulları için Releases sayfasına bak.", legalText:"Yalnızca sahibi olduğun veya indirilmesine izin verilen içerikleri indir. Platformların kullanım koşullarına uy. Arnold DW, YouTube veya Instagram ile bağlantılı ya da onlar tarafından desteklenen bir ürün değildir. Markalar sahiplerine aittir.", legalLink:"Yasal uyarının tamamı →", closingEyebrow:"HAZIR OLDUĞUNDA", closingTitle:"Daha sade bir indirme deneyimi.", rights:"Tüm hakları saklıdır.", github:"GitHub deposu ↗"
  },
  en: {
    description:"Arnold DW is a Windows desktop app that helps you manage YouTube and Instagram content on your computer.",
    ogDescription:"Preview, choose, and download YouTube videos and Instagram content on your Windows computer.",
    skip:"Skip to content", navLabel:"Main navigation", navFeatures:"Features", navHow:"How it works", navFaq:"FAQ",
    eyebrow:"DESKTOP APP FOR WINDOWS", heroTitle:'Your media,<br><span>your call.</span>', heroLead:"Preview, choose, and download YouTube videos and Instagram content to your computer. Simple, fast, in your hands.", download:"Download for Windows", explore:"Explore features", heroNote:"Windows desktop app", shotCaption:"Preview. Choose. Download.", heroFoot:"You decide what to download.",
    featuresEyebrow:"LESS FRICTION, MORE CONTROL", featuresTitle:'Everything you need.<br><span>Nothing extra.</span>', youtubeTitle:"YouTube, your way", youtubeText:"Preview your video first. Choose video quality for MP4 or bitrate for MP3. Track progress or cancel a download at any time.", previewChip:"Preview", instagramTitle:"Choose what to save on Instagram", instagramText:"Select individual post and carousel items. For public profiles, choose posts, reels, or the profile photo.", controlTitle:"Choose where files go", controlText:"Save downloads to the folder you want. Your choice is remembered next time.",
    howEyebrow:"THREE STEPS", howTitle:"From link to file.", step1Title:"Add a link", step1Text:"Paste a YouTube video or Instagram post/profile link.", step2Title:"Preview and choose", step2Text:"Review the content and choose a quality or the items to download.", step3Title:"Download", step3Text:"Start the download, follow its progress, and cancel if you need to.", faqEyebrow:"GOOD TO KNOW", faqTitle:"Quick answers.", faq1q:"Which platforms are supported?", faq1a:"YouTube individual videos, Instagram posts, and public profiles are currently supported. TikTok is not currently working.", faq2q:"Where are downloads saved?", faq2a:"The default location is the Arnold DW folder in Downloads. You can choose a different folder in the app, and it will be remembered.", faq3q:"Can I download a private Instagram profile?", faq3a:"No. Only the profile photo is available for private profiles.", faq4q:"Is the download free?", faq4a:"The app is distributed through GitHub Releases. Check the Releases page for current versions and distribution terms.", legalText:"Only download content you own or are authorized to download. Follow platform terms. Arnold DW is not affiliated with or endorsed by YouTube or Instagram. Trademarks belong to their owners.", legalLink:"Read the full disclaimer →", closingEyebrow:"WHEN YOU'RE READY", closingTitle:"A simpler way to download.", rights:"All rights reserved.", github:"GitHub repository ↗"
  }
};

const langButton = document.querySelector("[data-lang-toggle]");
const supported = ["tr", "en"];
function applyLanguage(lang) {
  const selected = supported.includes(lang) ? lang : "tr";
  document.documentElement.lang = selected;
  document.querySelector('meta[name="description"]').setAttribute("content", copy[selected].description);
  document.querySelector('meta[property="og:description"]').setAttribute("content", copy[selected].ogDescription);
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const value = copy[selected][element.dataset.i18n];
    if (value !== undefined) element.innerHTML = value;
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((element) => {
    const value = copy[selected][element.dataset.i18nAria];
    if (value !== undefined) element.setAttribute("aria-label", value);
  });
  langButton.textContent = selected === "tr" ? "EN" : "TR";
  langButton.setAttribute("aria-label", selected === "tr" ? "Switch language to English" : "Dili Türkçeye geçir");
  try { localStorage.setItem("arnold-dw-language", selected); } catch (_) { /* Storage can be unavailable. */ }
}
let initialLanguage = "tr";
try {
  const savedLanguage = localStorage.getItem("arnold-dw-language");
  if (supported.includes(savedLanguage)) initialLanguage = savedLanguage;
} catch (_) { /* Keep the default language when storage is unavailable. */ }
langButton.addEventListener("click", () => applyLanguage(document.documentElement.lang === "tr" ? "en" : "tr"));
document.querySelector("[data-year]").textContent = new Date().getFullYear();
applyLanguage(initialLanguage);
