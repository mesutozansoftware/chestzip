## ChestZip — açık kaynaklı arşiv yöneticisi

Ek bir program kurmanız gerekmez; RAR desteği dahil her şey paketin içindedir.

### İndirme

| Sistem | Dosya |
|---|---|
| Windows (önerilen) | `ChestZip-*-setup-windows-x64.exe` — kurulum, `.chz` ilişkilendirmesi |
| Windows (taşınabilir) | `ChestZip-*-windows-x64.zip` |
| macOS (Apple Silicon) | `ChestZip-*-macos-arm64.zip` |
| Ubuntu / Debian | `chestzip_*_amd64.deb` → `sudo apt install ./chestzip_*_amd64.deb` |
| Diğer Linux | `ChestZip-*-linux-x64.tar.gz` → açıp `./linux-install.sh` |
| pip | `pip install chestzip` |

Dosyaların SHA-256 özetleri `SHA256SUMS.txt` içindedir.

### İlk açılışta uyarı

Uygulama henüz ücretli bir kod imzalama sertifikasıyla imzalanmadığı için:

* **Windows:** "Windows bilgisayarınızı korudu" uyarısında *Ek bilgi → Yine de çalıştır*.
* **macOS:** İlk açılışta engellenirse *Sistem Ayarları → Gizlilik ve Güvenlik →
  Yine de Aç*.

### Özellikler

* Kendi açık biçimi **CHZ (.chz)**: solid LZMA2, AES-256-GCM, gizli dosya adları
* ZIP, 7Z, TAR, TAR.GZ/BZ2/XZ, GZ/BZ2/XZ oluşturma ve açma; RAR açma
* Zip bombası, Zip Slip ve kötü niyetli bağlantılara karşı koruma
* Windows, macOS ve Linux'ta aynı arayüz; Türkçe ve İngilizce
