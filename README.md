# Sandık

**Açık kaynaklı, çapraz platform arşiv yöneticisi.** Windows, macOS ve Linux'ta
birebir aynı arayüzle çalışır ve zip bombalarına karşı yerleşik korumaya sahiptir.

WinRAR'a benzer bir iş akışı sunar (araç çubuğu, arşiv içinde klasör gezme,
sürükle-bırak, şifreli arşivler), fakat **WinRAR ile hiçbir bağlantısı yoktur**.

## Özellikler

| Biçim | Oluştur | Aç / Çıkart | Ekle | Sil | Şifre |
|---|:-:|:-:|:-:|:-:|:-:|
| ZIP | ✔ | ✔ | ✔ | ✔ | AES-256 |
| 7Z | ✔ | ✔ | ✔ | – | AES-256 + gizli dosya adları |
| TAR, TAR.GZ, TAR.BZ2, TAR.XZ | ✔ | ✔ | ✔ | ✔ | – |
| GZ, BZ2, XZ (tek dosya) | ✔ | ✔ | – | – | – |
| RAR | – | ✔ (harici araçla) | – | – | – |

* Arşiv içinde klasör klasör gezinme; boyut, sıkışık boyut, oran, CRC sütunları
* Sürükle-bırak: dosyaları pencereye bırakınca arşivlenir, arşivden dışarı sürüklenir
* Arşivdeki dosyayı çift tıklayınca görüntüleme
* Bütünlük testi (CRC), arşiv bilgisi ve güvenlik analizi
* Üzerine yazma seçenekleri: sor / üzerine yaz / atla / otomatik yeniden adlandır
* Türkçe ve İngilizce arayüz, açık ve koyu tema
* Komut satırı arayüzü (`sandik l/x/a/t/d`)

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

## Kurulum ve çalıştırma

Hazır paketler: GitHub'da bir `v*` etiketi gönderildiğinde Actions iş akışı
Windows (`.zip`), macOS (`.app`) ve Linux (`.tar.gz`) paketlerini otomatik üretir.

Kaynaktan (Python 3.10+):

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/sandik
```

Windows'ta `.venv\Scripts\sandik.exe` kullanın.

### Komut satırı

```bash
sandik a yedek.7z Belgeler/ -p gizli    # şifreli 7z oluştur
sandik l yedek.7z -p gizli              # listele (+ güvenlik analizi)
sandik x yedek.7z -o hedef/ -p gizli    # çıkart
sandik t arsiv.zip                      # test et
sandik d arsiv.zip eski/                # arşivden sil
sandik x supheli.zip --max-ratio 100 --max-size 2G
```

### Kendi paketini derleme

```bash
pip install . pyinstaller && python packaging/make_icons.py && pyinstaller packaging/sandik.spec
```

Çıktı `dist/` klasörüne yazılır (macOS'ta `Sandık.app`). Paketlenmiş Windows
sürümü konsolsuz derlendiği için komut satırı kullanımı için `pip` kurulumunu tercih edin.

### RAR açma

RAR açmak için sistemde şu araçlardan biri bulunmalı: `unrar`, `unar`, `7z` veya
`bsdtar` (macOS ve Windows 10+ ile birlikte gelir; şifreli RAR desteklemez).

## Hukuki notlar

* Sandık MIT lisanslıdır ve tamamen özgün koddan oluşur.
* WinRAR'ın adını, logosunu, ikonlarını, kodunu veya arayüz görsellerini kullanmaz.
  Tüm ikonlar bu projede SVG olarak çizilmiştir.
* **RAR arşivi oluşturulmaz.** RAR sıkıştırma algoritması tescillidir; unRAR lisansı da
  kodunun RAR sıkıştırıcı yapmak için kullanılmasını yasaklar. Sandık unRAR kodunu
  içermez; RAR açma yalnızca kullanıcının sisteminde kurulu harici bir araçla yapılır.
* ZIP, 7z, tar, gzip, bzip2 ve xz açık biçimlerdir.
* Bağımlılık lisansları: PySide6/Qt (LGPLv3), py7zr (LGPL-2.1), pyzipper (MIT),
  rarfile (ISC). LGPL kütüphaneler değiştirilmeden, dinamik olarak kullanılır.

## Proje yapısı

```
sandik/
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
