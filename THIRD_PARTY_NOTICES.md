# Üçüncü taraf bileşenler / Third-party notices

ChestZip kendi kodu MIT lisanslıdır. Paketlenmiş sürümler aşağıdaki bileşenleri
değiştirilmeden içerir.

## 7-Zip (`7zz`) — RAR açmak için

* Telif hakkı (C) 1999-2026 Igor Pavlov — https://www.7-zip.org
* Lisans: GNU LGPL v2.1 veya sonrası (+ bazı dosyalar için BSD lisansları) ve
  aşağıdaki unRAR kısıtlaması. Kaynak kod: https://www.7-zip.org/download.html
* ChestZip programı değiştirmeden, ayrı bir çalıştırılabilir dosya olarak dağıtır
  ve yalnızca RAR **açmak** için çağırır. `py7zz` paketi (MIT) aracılığıyla gelir.

**unRAR kısıtlaması:** 7-Zip'teki RAR açma motoru, Alexander Roshal'a ait unRAR
kaynak kodu kullanılarak geliştirilmiştir. unRAR lisansının kısıtlaması şudur:
unRAR kaynakları, tescilli olan RAR sıkıştırma algoritmasını yeniden oluşturmak
için kullanılamaz. Değiştirilmiş unRAR kaynaklarının ayrı olarak veya başka bir
yazılımın parçası olarak dağıtılmasına, belgelerde ve kaynak yorumlarında kodun
RAR (WinRAR) uyumlu bir arşivleyici geliştirmek için kullanılamayacağının açıkça
belirtilmesi koşuluyla izin verilir.

ChestZip RAR arşivi **oluşturmaz**; bu kısıtlamaya uyar.

## Diğer kütüphaneler

| Bileşen | Lisans | Kullanım |
|---|---|---|
| Qt / PySide6 | LGPL v3 | Arayüz (dinamik bağlantı, değiştirilmeden) |
| py7zr | LGPL v2.1+ | 7z okuma/yazma |
| pyzipper | MIT | AES şifreli ZIP |
| rarfile | ISC | RAR başlıklarını okuma |
| py7zz | MIT | 7-Zip programını sağlar |
| cryptography | Apache 2.0 / BSD | Başlığı şifreli RAR |

`tests/data/rar/` içindeki örnek RAR dosyaları rarfile projesinin (ISC) test
dosyalarıdır.

"RAR" ve "WinRAR", RARLAB'ın markalarıdır. ChestZip RARLAB ile bağlantılı değildir.
