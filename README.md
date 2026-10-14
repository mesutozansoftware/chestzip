# ChestZip

**Açık kaynaklı, çapraz platform arşiv yöneticisi.** Windows, macOS ve Linux'ta
birebir aynı arayüzle çalışır ve zip bombalarına karşı yerleşik korumaya sahiptir.

WinRAR'a benzer bir iş akışı sunar (araç çubuğu, arşiv içinde klasör gezme,
sürükle-bırak, şifreli arşivler), fakat **WinRAR ile hiçbir bağlantısı yoktur**.

## Kendi biçimimiz: CHZ (`.chz`)

WinRAR'ın `.rar`'ı gibi ChestZip'in de kendi biçimi var. Farkı, CHZ'nin **açık ve
belgeli** olması: [docs/CHZ_FORMAT.md](docs/CHZ_FORMAT.md).

* **Güçlü sıkıştırma:** Solid bloklar + LZMA2. Oran 7z ile aynı seviyede.
* **AES-256-GCM şifreleme:** Şifrelenince dosya adları da gizlenir.
* **Bütünlük:** Her dosyanın BLAKE2b-256 özetiyle doğrulanır.
* **Zip bombasına dayanıklı tasarım:** Blok boyutu sınırları, verinin çoğaltılması
  yasak, kesin boyut kontrolü.
* **Hızlı tek dosya çıkarma:** Arşivin tamamını açmak gerekmez.
* **Varsayılan biçim:** Yeni arşivler CHZ olarak oluşturulur; `.chz` dosyaları
  çift tıklayınca ChestZip'te açılır.

Örnek ölçüm (16,5 MB, 1439 dosyalık Python kaynak kodu, seviye "Normal"):

| Biçim | Boyut | Oran | Test süresi |
|---|---|---|---|
| CHZ | 3,72 MB | %22,5 | 0,3 s |
| 7Z | 3,58 MB | %21,7 | 0,5 s |
| TAR.XZ | 3,65 MB | %22,1 | 0,7 s |
| ZIP | 6,38 MB | %38,7 | 0,1 s |

## Özellikler

| Biçim | Oluştur | Aç / Çıkart | Ekle | Sil | Şifre |
|---|:-:|:-:|:-:|:-:|:-:|
| **CHZ (kendi biçimi)** | ✔ | ✔ | ✔ | ✔ | AES-256-GCM + gizli dosya adları |
| ZIP | ✔ | ✔ | ✔ | ✔ | AES-256 |
| 7Z | ✔ | ✔ | ✔ | – | AES-256 + gizli dosya adları |
| TAR, TAR.GZ, TAR.BZ2, TAR.XZ | ✔ | ✔ | ✔ | ✔ | – |
| GZ, BZ2, XZ (tek dosya) | ✔ | ✔ | – | – | – |
| RAR (RAR4, RAR5) | – | ✔ | – | – | ✔ (açarken) |

* Arşiv içinde klasör klasör gezinme; boyut, sıkışık boyut, oran, CRC sütunları
* Sürükle-bırak: dosyaları pencereye bırakınca arşivlenir, arşivden dışarı sürüklenir
* Arşivdeki dosyayı çift tıklayınca görüntüleme
* Bütünlük testi (CRC), arşiv bilgisi ve güvenlik analizi
* Üzerine yazma seçenekleri: sor / üzerine yaz / atla / otomatik yeniden adlandır
* Türkçe ve İngilizce arayüz, açık ve koyu tema
* Komut satırı arayüzü (`chestzip l/x/a/t/d`)

## Güvenlik: zip bombası ve diğer saldırılara karşı koruma

Arşiv başlıklarındaki boyut bilgilerine **güvenilmez**. Başlıklar yalnızca hızlı ön
kontrol için kullanılır; asıl denetim veri açılırken bayt bayt yapılır. Sınır aşıldığında
işlem durur ve yarım kalan dosya silinir (veri önce geçici dosyaya yazılır).

| Saldırı | Koruma |
|---|---|
| Klasik zip bombası (aşırı yüksek sıkıştırma) | Dosya başına ve toplam **gerçek** oran sınırı (varsayılan 1000:1) |
| Başlıkta yalan boyut söyleyen arşiv | Açılan veri akış hâlinde sayılır, başlığa bakılmaz |
| tar.gz / gz bombası (başlıkta boyut yok) | Açılan akış sayaçtan geçer (`StreamGuard`) |
| Üst üste binen ZIP kayıtları (Fifield tipi özyinelemesiz bomba) | Yerel başlık aralıkları karşılaştırılır, çakışma varsa reddedilir |
| İç içe arşiv bombası (42.zip) | İç arşivler asla otomatik açılmaz |
| Diski doldurma | Toplam boyut sınırı (varsayılan 20 GB) + diskte her zaman 1 GB boş bırakma |
| Çok sayıda dosya | Kayıt sayısı sınırı (varsayılan 250.000) |
| Zip Slip / path traversal (`../../`, `C:\`, `\\server`) | `..` içeren kayıtlar atlanır, mutlak yollar hedef içine alınır, son yol `realpath` ile doğrulanır |
| Hedef dışını gösteren symlink | Varsayılan olarak bağlantı oluşturulmaz; açılırsa yalnızca hedef içini gösterenlere izin verilir |
| Aygıt dosyaları, setuid bitleri | Atlanır / temizlenir |
| Windows ayrılmış adları (`CON`, `NUL`…) | Yeniden adlandırılır |

Sınırlar **Ayarlar → Zip bombası ve güvenlik** bölümünden değiştirilebilir. Koruma
kapatılsa bile yol güvenliği (Zip Slip) her zaman açıktır.

## Kurulum

Ek bir program (Python, 7-Zip vb.) kurmanız gerekmez. Hazır paketler
[Releases](https://github.com/mesutozansoftware/chestzip/releases/latest) sayfasındadır.

**Tek satırla kurulum** (son sürümü indirir, SHA-256 ile doğrular, yönetici yetkisi istemez):

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/mesutozansoftware/chestzip/main/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/mesutozansoftware/chestzip/main/install.ps1 | iex
```

Ya da paketi elle indirin:

| Sistem | Nasıl kurulur |
|---|---|
| **Windows** | `ChestZip-…-setup-windows-x64.exe` kurulum programını çalıştırın (`.chz` dosyaları ilişkilendirilir). Kurulumsuz kullanım için `…-windows-x64.zip`. |
| **macOS (Homebrew)** | `brew install --cask mesutozansoftware/chestzip/chestzip` |
| **macOS (elle)** | `ChestZip-…-macos-arm64.zip` dosyasını açıp `ChestZip.app`'i Uygulamalar'a sürükleyin. (Apple Silicon) |
| **Ubuntu / Debian** | `sudo apt install ./chestzip_…_amd64.deb` |
| **Linux (Flatpak)** | `flatpak install --user ChestZip-…-linux-x64.flatpak` |
| **Diğer Linux** | `ChestZip-…-linux-x64.tar.gz` dosyasını açıp `./linux-install.sh` |

**İlk açılış uyarısı:** Uygulama henüz ücretli bir kod imzalama sertifikasıyla
imzalanmadığı için Windows "bilgisayarınızı korudu" uyarısı gösterebilir
(*Ek bilgi → Yine de çalıştır*). macOS'ta ise *Sistem Ayarları → Gizlilik ve
Güvenlik → Yine de Aç* gerekebilir.

### Kaynaktan çalıştırma (geliştiriciler için, Python 3.10+)

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/chestzip
```

Windows'ta `.venv\Scripts\chestzip.exe` kullanın.

### Komut satırı

```bash
chestzip a yedek.chz Belgeler/ -p gizli   # şifreli CHZ oluştur (varsayılan biçim)
chestzip a yedek.7z Belgeler/ -p gizli    # şifreli 7z oluştur
chestzip l yedek.7z -p gizli              # listele (+ güvenlik analizi)
chestzip x yedek.7z -o hedef/ -p gizli    # çıkart
chestzip t arsiv.zip                      # test et
chestzip d arsiv.zip eski/                # arşivden sil
chestzip x supheli.zip --max-ratio 100 --max-size 2G
```

### Dosya ilişkilendirme (`.chz` çift tıklayınca açılsın)

* **macOS:** `ChestZip.app` bir kez açıldığında `.chz` türü sisteme tanıtılır.
* **Windows:** Kurulum programı `.chz`'yi ilişkilendirir.
* **Linux:** `.deb` ve Flatpak paketleri otomatik ilişkilendirir; `.tar.gz` için
  `./linux-install.sh`.

### Kendi paketini derleme

```bash
pip install . pyinstaller && python packaging/make_icons.py && pyinstaller packaging/chestzip.spec
```

Çıktı `dist/` klasörüne yazılır (macOS'ta `ChestZip.app`). Paketlenmiş Windows
sürümü konsolsuz derlendiği için komut satırı kullanımı için `pip` kurulumunu tercih edin.

### RAR açma

Ek bir şey kurmanız gerekmez. ChestZip, RAR açmak için resmi 7-Zip programını
(`7zz`) içinde taşır; Windows, macOS ve Linux'ta aynı çözücü kullanılır. Şifreli ve
başlığı şifreli RAR'lar da açılır. Açılan veri yine ChestZip'in güvenlik
katmanından (zip bombası, Zip Slip koruması) geçer.

## Hukuki notlar

* ChestZip MIT lisanslıdır ve tamamen özgün koddan oluşur.
* WinRAR'ın adını, logosunu, ikonlarını, kodunu veya arayüz görsellerini kullanmaz.
  Tüm ikonlar bu projede SVG olarak çizilmiştir.
* **RAR arşivi oluşturulmaz.** RAR sıkıştırma algoritması tescillidir; unRAR lisansı da
  kodunun RAR sıkıştırıcı yapmak için kullanılmasını yasaklar.
* **RAR açmak serbesttir.** RAR açma, değiştirilmemiş resmi 7-Zip programıyla yapılır;
  7-Zip'in lisansı RAR açmaya izin verir, yalnızca RAR oluşturmayı yasaklar. Ayrıntılar
  ve lisans metinleri: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
* "RAR" ve "WinRAR" RARLAB'ın markalarıdır; bu yüzden uygulamanın adında kullanılmaz.
* ZIP, 7z, tar, gzip, bzip2 ve xz açık biçimlerdir.
* Bağımlılık lisansları: PySide6/Qt (LGPLv3), py7zr (LGPL-2.1), pyzipper (MIT),
  rarfile (ISC), py7zz (MIT), 7-Zip (LGPL + unRAR kısıtlaması), cryptography (Apache/BSD).
  LGPL bileşenler değiştirilmeden kullanılır.

## Proje yapısı

```
chestzip/
  safety.py          güvenlik katmanı (sınırlar, yol doğrulama, akış sayaçları)
  api.py             üst düzey API (Archive, create_archive)
  backends/          zip, 7z, tar/gz/bz2/xz, rar arka uçları
  cli.py             komut satırı
  gui/               PySide6 arayüzü (Fusion stili, özgün ikonlar)
tests/               pytest testleri (bomba ve saldırı senaryoları dahil)
packaging/           PyInstaller, ikon üretici, Linux .desktop dosyası
```

Testleri çalıştırmak için:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
```
