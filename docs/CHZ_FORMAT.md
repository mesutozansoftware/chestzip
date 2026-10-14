# CHZ arşiv biçimi — sürüm 1

`.chz`, ChestZip'in kendi arşiv biçimidir. Açık ve belgelidir: bu belgeye bakarak
herkes CHZ okuyan/yazan bir program yazabilir. Patent, lisans ücreti veya kısıtlama
yoktur. MIME türü: `application/x-chestzip`.

Bütün tamsayılar **little-endian**'dır.

## Genel yerleşim

```
+-----------------------------+
| Başlık (16 bayt)            |
| Şifreleme bloğu (20 bayt)   |  yalnızca şifreliyse
| Blok 0 .. Blok N-1          |  sıkıştırılmış (ve/veya şifrelenmiş) veri
| Dizin                       |  sıkıştırılmış (ve/veya şifrelenmiş) JSON
| Son ek (48 bayt)            |
+-----------------------------+
```

### Başlık (16 bayt)

| Ofset | Boyut | Alan |
|---|---|---|
| 0 | 8 | Sihirli sayı `43 48 5A 21 1A 0D 0A 00` (`CHZ!\x1a\r\n\0`) |
| 8 | 1 | Sürüm (= 1). Okuyucu daha büyük sürümleri reddetmelidir. |
| 9 | 1 | Bayraklar. Bit 0: şifreli. Diğer bitler 0. |
| 10 | 6 | Ayrılmış (0) |

### Şifreleme bloğu (20 bayt, bayrak bit 0 = 1 ise)

| Ofset | Boyut | Alan |
|---|---|---|
| 0 | 16 | scrypt tuzu (rastgele) |
| 16 | 1 | log2(N) — okuyucu 10..20 dışını reddeder |
| 17 | 1 | r — okuyucu 1..16 dışını reddeder |
| 18 | 1 | p — okuyucu 1..4 dışını reddeder |
| 19 | 1 | Ayrılmış (0) |

Anahtar: `key = scrypt(UTF-8(parola), tuz, N, r, p, uzunluk=32)`. Varsayılan
N=2^15, r=8, p=1. Şifre AES-256-GCM'dir (12 bayt nonce, 16 bayt etiket).

### Son ek (48 bayt, dosyanın sonunda)

| Ofset | Boyut | Alan |
|---|---|---|
| 0 | 8 | Dizin ofseti |
| 8 | 8 | Dizinin dosyadaki (saklı) boyutu |
| 16 | 8 | Dizinin açılmış (JSON) boyutu — okuyucu 256 MiB üstünü reddeder |
| 24 | 12 | Dizin nonce'u (şifresizse sıfır) |
| 36 | 4 | İlk 36 baytın CRC-32'si |
| 40 | 8 | `CHZ-END\0` |

Dizin, son ekten hemen önce biter: `dizin ofseti + saklı boyut = dosya boyutu - 48`.

## Sıkıştırma

Hem bloklar hem dizin **ham LZMA2** akışıdır (`.xz` kabı olmadan). Açıcının
sözlük boyutu, verinin açılmış boyutunu aşmayan en küçük 2'nin kuvvetidir
(en az 4096). Bu, açarken kullanılan belleği veri boyutuyla sınırlar.

Açılan verinin boyutu tam olarak bildirilen boyut olmalı ve LZMA2 akışı orada
bitmelidir. Fazla veya eksik veri hatadır (bomba koruması).

## Dizin

Dizin şu adımlarla oluşur: UTF-8 JSON → LZMA2 → (şifreliyse) AES-GCM. Şifrelemede
nonce son ekteki nonce, ek doğrulanmış veri (AAD) ise `CHZ1-index` olur. Şifreli
arşivlerde dosya adları dahil bütün dizin gizlidir.

```json
{
  "v": 1,
  "b": [[ofset, saklı_boyut, açılmış_boyut, yöntem, "nonce_hex"], ...],
  "e": [
    {"n": "klasör/dosya.txt", "t": "f", "s": 1234, "m": 1760000000.0, "p": 420,
     "h": "<BLAKE2b-256 hex>", "g": [[blok, blok_içi_ofset, uzunluk], ...]},
    {"n": "klasör", "t": "d", "m": 1760000000.0}
  ]
}
```

* `b` — bloklar. `yöntem`: 0 = saklı (sıkıştırmasız), 1 = LZMA2. `nonce_hex`,
  şifreli arşivde 24 hex karakter, şifresizde boş metindir.
* `e` — kayıtlar. `n`: `/` ile ayrılmış yol; `t`: `f` dosya, `d` klasör;
  `s`: boyut; `m`: değiştirilme zamanı (Unix saniyesi, isteğe bağlı);
  `p`: Unix izinleri (isteğe bağlı); `h`: dosya içeriğinin BLAKE2b-256 özeti;
  `g`: dosyanın sırasıyla birleştirilen blok parçaları.

## Bloklar (solid sıkıştırma)

Yazıcı, dosya içeriklerini sırayla bir arabelleğe ekler ve arabellek `BLOCK`
(varsayılan 8 MiB) dolunca bir blok yazar. Böylece küçük dosyalar aynı blokta
birlikte sıkıştırılır, büyük dosyalar birden çok bloğa yayılır. Blok küçülmüyorsa
sıkıştırmadan saklanır (yöntem 0).

Şifreliyse her blok, kendi rastgele 12 baytlık nonce'u ve `CHZ1-block` AAD'si ile
AES-256-GCM'den geçer. Nonce'lar şifreli dizinde tutulur; dizin de GCM ile
doğrulandığı için bloklar yer değiştiremez veya değiştirilemez.

## Okuyucunun yapması GEREKEN kontroller

1. Sürüm ≤ 1; scrypt parametreleri sınırlar içinde.
2. Son ek CRC'si doğru; dizin konumu tutarlı; açılmış dizin ≤ 256 MiB.
3. Her blok: `açılmış_boyut ≤ 64 MiB`; veri alanı içinde (başlıktan sonra,
   dizinden önce); yöntem 0 ise `saklı = açılmış (+16 şifreliyse)`.
4. Bloklar dosyada **üst üste binmez**.
5. Her parça kendi bloğunun sınırları içindedir ve bir bloğun her baytı **en fazla
   bir** dosya parçasına aittir. Bu, aynı veriyi binlerce dosyaya gösterip çoğaltan
   özyinelemesiz zip bombasını engeller.
6. Parça uzunluklarının toplamı `s`'ye eşittir; açılan içerik `h` özetiyle doğrulanır.
7. Yollar çıkartılırken güvenli hâle getirilir: `..` içeren kayıtlar atlanır,
   mutlak yollar ve sürücü harfleri temizlenir.

## Neden bu tasarım?

| Hedef | Çözüm |
|---|---|
| Yüksek oran | Solid bloklar + LZMA2 (7z ile benzer oran) |
| Hızlı tek dosya açma | Bağımsız bloklar: en fazla birkaç blok açılır |
| Gizlilik | AES-256-GCM, scrypt, dizin (dosya adları) şifreli |
| Bütünlük | Dosya başına BLAKE2b-256 + GCM doğrulama etiketleri |
| Zip bombasına dayanıklılık | Boyut sınırları, üst üste binme ve paylaşım yasağı, kesin boyut kontrolü |
| Kolay uygulama | Sabit başlık/son ek + JSON dizin; her dilde yazılabilir |
