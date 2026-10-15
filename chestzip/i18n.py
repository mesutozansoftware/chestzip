"""Basit iki dilli (Türkçe / İngilizce) çeviri tablosu."""

from __future__ import annotations

import locale
import os

_LANG = "tr"

STRINGS: dict[str, tuple[str, str]] = {
    # ---- hatalar / güvenlik ------------------------------------------------
    "err.unsafe_path": ("Güvensiz yol atlandı: {name}", "Unsafe path skipped: {name}"),
    "err.cancelled": ("İşlem iptal edildi.", "Operation cancelled."),
    "err.dir_conflict": ("Aynı adda klasör/dosya çakışması, atlandı: {name}",
                         "File/folder name conflict, skipped: {name}"),
    "err.unknown_format": ("Tanınmayan veya bozuk arşiv: {path}",
                           "Unknown or corrupt archive: {path}"),
    "err.password_required": ("Bu arşiv şifreli. Lütfen şifre girin.",
                              "This archive is encrypted. Please enter the password."),
    "err.wrong_password": ("Şifre yanlış veya arşiv bozuk.",
                           "Wrong password or corrupt archive."),
    "err.no_delete": ("{fmt} biçimi dosya silmeyi desteklemiyor.",
                      "The {fmt} format does not support deleting files."),
    "err.no_add": ("{fmt} biçimine dosya eklenemez.", "Files cannot be added to {fmt}."),
    "err.single_file": ("{fmt} biçimi yalnızca tek bir dosya içerebilir. TAR.{up} kullanın.",
                        "{fmt} can hold only a single file. Use TAR.{up} instead."),
    "err.rar_create": ("RAR oluşturma desteklenmez: RAR sıkıştırma algoritması tescillidir. "
                       "ZIP veya 7Z kullanın.",
                       "Creating RAR is not supported: the RAR compression algorithm is "
                       "proprietary. Use ZIP or 7Z."),
    "err.rar_tool": ("RAR çözücüsü (gömülü 7-Zip) bulunamadı; uygulama eksik kurulmuş olabilir.",
                     "RAR decoder (bundled 7-Zip) not found; the installation may be incomplete."),
    "err.no_password_support": ("{fmt} biçimi şifrelemeyi desteklemiyor. CHZ, ZIP veya 7Z seçin.",
                                "{fmt} does not support encryption. Choose CHZ, ZIP or 7Z."),
    "err.corrupt": ("Arşiv bozuk: {detail}", "Archive is corrupt: {detail}"),
    "sec.unsafe_paths": ("{n} kayıt hedef klasörün dışına yazmaya çalışıyor (ör. {first}); "
                         "bunlar atlanacak.",
                         "{n} entries try to write outside the target folder (e.g. {first}); "
                         "they will be skipped."),
    "sec.links": ("{n} sembolik/sabit bağlantı var; güvenlik için varsayılan olarak "
                  "oluşturulmaz.",
                  "{n} symbolic/hard links found; by default they are not created."),
    "sec.entry_ratio": ("Zip bombası şüphesi: '{name}' sıkıştırma oranı {ratio:.0f}:1 "
                        "(sınır {max:.0f}:1).",
                        "Possible zip bomb: '{name}' compression ratio {ratio:.0f}:1 "
                        "(limit {max:.0f}:1)."),
    "sec.total_ratio": ("Zip bombası şüphesi: toplam sıkıştırma oranı {ratio:.0f}:1 "
                        "(sınır {max:.0f}:1).",
                        "Possible zip bomb: overall compression ratio {ratio:.0f}:1 "
                        "(limit {max:.0f}:1)."),
    "sec.too_many": ("Arşivde çok fazla kayıt var: {n} (sınır {max}).",
                     "Too many entries in archive: {n} (limit {max})."),
    "sec.too_big": ("Açılmış toplam boyut {size}, sınır {max}.",
                    "Total unpacked size {size} exceeds limit {max}."),
    "sec.no_space": ("Yetersiz disk alanı: {size} gerekiyor, boş alan {free}.",
                     "Not enough disk space: {size} needed, {free} free."),
    "sec.stream_too_big": ("Zip bombası koruması: açılan veri {max} sınırını aştı, "
                           "işlem durduruldu.",
                           "Zip bomb protection: unpacked data exceeded {max}, aborted."),
    "sec.stream_ratio": ("Zip bombası koruması: gerçek sıkıştırma oranı {ratio:.0f}:1, "
                         "sınır {max:.0f}:1. İşlem durduruldu.",
                         "Zip bomb protection: actual compression ratio {ratio:.0f}:1 "
                         "exceeds {max:.0f}:1. Aborted."),
    "sec.disk_full": ("Disk doldurma koruması: boş alan rezervine ulaşıldı, işlem durduruldu.",
                      "Disk protection: free-space reserve reached, aborted."),
    "sec.overlap": ("Zip bombası tespit edildi: ZIP kayıtları üst üste biniyor "
                    "(özyinelemesiz bomba tekniği).",
                    "Zip bomb detected: ZIP entries overlap (non-recursive bomb technique)."),
    "sec.link_skipped": ("Bağlantı oluşturulmadı: {name} -> {target}",
                         "Link not created: {name} -> {target}"),
    "sec.link_outside": ("Hedef dışını gösteren bağlantı engellendi: {name} -> {target}",
                         "Blocked link pointing outside target: {name} -> {target}"),
    "sec.special_skipped": ("Özel dosya (aygıt/FIFO) atlandı: {name}",
                            "Special file (device/FIFO) skipped: {name}"),
    "sec.nested": ("{n} iç içe arşiv var; bunlar otomatik açılmaz.",
                   "{n} nested archives found; they are never auto-extracted."),
    # ---- arayüz ----------------------------------------------------------------
    "app.tagline": ("Açık kaynaklı arşiv yöneticisi", "Open-source archive manager"),
    "menu.file": ("&Dosya", "&File"),
    "menu.commands": ("&Komutlar", "&Commands"),
    "menu.options": ("&Seçenekler", "&Options"),
    "menu.help": ("&Yardım", "&Help"),
    "act.open": ("Arşiv aç...", "Open archive..."),
    "act.open_folder": ("Klasöre git...", "Go to folder..."),
    "act.quit": ("Çıkış", "Quit"),
    "act.add": ("Ekle", "Add"),
    "act.extract": ("Çıkart", "Extract To"),
    "act.extract_here": ("Buraya çıkart", "Extract here"),
    "act.test": ("Test", "Test"),
    "act.view": ("Görüntüle", "View"),
    "act.delete": ("Sil", "Delete"),
    "act.info": ("Bilgi", "Info"),
    "act.convert": ("Dönüştür", "Convert"),
    "act.settings": ("Ayarlar", "Settings"),
    "act.up": ("Üst klasör", "Up one level"),
    "act.about": ("Hakkında", "About"),
    "act.select_all": ("Tümünü seç", "Select all"),
    "act.language": ("Dil", "Language"),
    "act.theme": ("Tema", "Theme"),
    "theme.light": ("Açık", "Light"),
    "theme.dark": ("Koyu", "Dark"),
    "col.name": ("Ad", "Name"),
    "col.size": ("Boyut", "Size"),
    "col.packed": ("Sıkışık", "Packed"),
    "col.ratio": ("Oran", "Ratio"),
    "col.type": ("Tür", "Type"),
    "col.modified": ("Değiştirilme", "Modified"),
    "col.crc": ("CRC32", "CRC32"),
    "type.folder": ("Klasör", "Folder"),
    "type.file": ("{ext} dosyası", "{ext} file"),
    "type.file_plain": ("Dosya", "File"),
    "type.archive": ("{fmt} arşivi", "{fmt} archive"),
    "type.link": ("Bağlantı", "Link"),
    "status.items": ("{dirs} klasör, {files} dosya — toplam {size}",
                     "{dirs} folders, {files} files — total {size}"),
    "status.selected": ("Seçili: {n} öğe, {size}", "Selected: {n} items, {size}"),
    "status.safety_on": ("🛡 Zip bombası koruması açık", "🛡 Zip bomb protection on"),
    "status.safety_off": ("⚠ Koruma kapalı", "⚠ Protection off"),
    "status.encrypted": ("🔒 Şifreli", "🔒 Encrypted"),
    "dlg.error": ("Hata", "Error"),
    "dlg.warning": ("Uyarı", "Warning"),
    "dlg.done": ("Tamamlandı", "Done"),
    "dlg.password": ("Şifre girin", "Enter password"),
    "dlg.password_for": ("'{name}' için şifre:", "Password for '{name}':"),
    "dlg.show_password": ("Şifreyi göster", "Show password"),
    "dlg.confirm_delete": ("Seçili {n} öğe arşivden kalıcı olarak silinsin mi?",
                           "Permanently delete {n} selected items from the archive?"),
    "dlg.overwrite_title": ("Dosya zaten var", "File already exists"),
    "dlg.overwrite_text": ("Bu dosya zaten var:\n{path}\n\nÜzerine yazılsın mı?",
                           "This file already exists:\n{path}\n\nOverwrite it?"),
    "btn.yes": ("Evet", "Yes"),
    "btn.yes_all": ("Tümüne evet", "Yes to all"),
    "btn.no": ("Hayır", "No"),
    "btn.no_all": ("Tümüne hayır", "No to all"),
    "btn.rename": ("Yeniden adlandır", "Rename"),
    "btn.cancel": ("İptal", "Cancel"),
    "btn.ok": ("Tamam", "OK"),
    "btn.browse": ("Gözat...", "Browse..."),
    "btn.reset": ("Varsayılanlar", "Defaults"),
    "add.title": ("Arşive ekle", "Add to archive"),
    "add.name": ("Arşiv adı:", "Archive name:"),
    "add.format": ("Biçim:", "Format:"),
    "add.level": ("Sıkıştırma:", "Compression:"),
    "add.password": ("Şifre (isteğe bağlı):", "Password (optional):"),
    "add.password2": ("Şifre tekrar:", "Repeat password:"),
    "add.mismatch": ("Şifreler eşleşmiyor.", "Passwords do not match."),
    "add.files": ("{n} öğe eklenecek", "{n} items will be added"),
    "add.encrypt_note": ("CHZ ve 7Z: AES-256 + dosya adları gizlenir • ZIP: AES-256",
                         "CHZ and 7Z: AES-256 + file names hidden • ZIP: AES-256"),
    "level.0": ("Depola (sıkıştırma yok)", "Store (no compression)"),
    "level.1": ("En hızlı", "Fastest"),
    "level.3": ("Hızlı", "Fast"),
    "level.5": ("Normal", "Normal"),
    "level.7": ("İyi", "Good"),
    "level.9": ("En iyi", "Best"),
    "ext.title": ("Çıkartma yolu ve seçenekleri", "Extraction path and options"),
    "ext.dest": ("Hedef klasör:", "Destination folder:"),
    "ext.overwrite": ("Var olan dosyalar:", "Existing files:"),
    "ext.ow.ask": ("Sor", "Ask"),
    "ext.ow.always": ("Üzerine yaz", "Overwrite"),
    "ext.ow.never": ("Atla", "Skip"),
    "ext.ow.rename": ("Otomatik yeniden adlandır", "Rename automatically"),
    "ext.subfolder": ("Arşiv adıyla alt klasör oluştur", "Create subfolder named after archive"),
    "ext.selected_only": ("Yalnızca seçili {n} öğe çıkartılacak", "Only {n} selected items"),
    "prog.title": ("İşlem sürüyor", "Working"),
    "prog.extracting": ("Çıkartılıyor", "Extracting"),
    "prog.adding": ("Ekleniyor", "Adding"),
    "prog.testing": ("Test ediliyor", "Testing"),
    "prog.deleting": ("Siliniyor", "Deleting"),
    "prog.opening": ("Açılıyor", "Opening"),
    "res.extracted": ("{files} dosya çıkartıldı ({size}).", "{files} files extracted ({size})."),
    "res.skipped": ("{n} öğe atlandı.", "{n} items skipped."),
    "res.test_ok": ("Test başarılı: {files} dosya, {size} — hata bulunamadı.",
                    "Test passed: {files} files, {size} — no errors found."),
    "res.created": ("Arşiv oluşturuldu: {path}", "Archive created: {path}"),
    "res.deleted": ("{n} öğe silindi.", "{n} items deleted."),
    "res.converted": ("Dönüştürüldü: {path}", "Converted: {path}"),
    "prog.converting": ("Dönüştürülüyor", "Converting"),
    "conv.title": ("Arşivi dönüştür", "Convert archive"),
    "conv.source": ("Kaynak: {name} ({fmt})", "Source: {name} ({fmt})"),
    "conv.same_file": ("Hedef dosya kaynakla aynı olamaz.",
                       "The target file cannot be the same as the source."),
    "conv.empty": ("Arşivde dönüştürülecek dosya yok.", "The archive has nothing to convert."),
    "conv.new_password": ("Yeni şifre (isteğe bağlı):", "New password (optional):"),
    "res.warnings": ("Uyarılar:", "Warnings:"),
    "info.title": ("Arşiv bilgisi", "Archive info"),
    "info.format": ("Biçim", "Format"),
    "info.path": ("Konum", "Location"),
    "info.size": ("Arşiv boyutu", "Archive size"),
    "info.unpacked": ("Açılmış boyut", "Unpacked size"),
    "info.entries": ("Kayıt sayısı", "Entries"),
    "cli.entries": ("{n} kayıt, {size}", "{n} entries, {size}"),
    "info.ratio": ("Sıkıştırma oranı", "Compression ratio"),
    "info.encrypted": ("Şifreli", "Encrypted"),
    "info.security": ("Güvenlik analizi", "Security analysis"),
    "info.secure": ("✔ Sorun bulunmadı", "✔ No issues found"),
    "set.title": ("Ayarlar", "Settings"),
    "set.safety": ("Zip bombası ve güvenlik", "Zip bomb & security"),
    "set.enabled": ("Zip bombası korumasını etkinleştir", "Enable zip bomb protection"),
    "set.max_total": ("En fazla açılmış boyut (GB):", "Max unpacked size (GB):"),
    "set.max_entries": ("En fazla dosya sayısı:", "Max number of files:"),
    "set.max_ratio": ("En yüksek sıkıştırma oranı (x:1):", "Max compression ratio (x:1):"),
    "set.ratio_grace": ("Oran kontrolü başlangıcı (MB):", "Ratio check starts after (MB):"),
    "set.disk_reserve": ("Diskte boş bırakılacak alan (MB):", "Disk free-space reserve (MB):"),
    "set.allow_symlinks": ("Güvenli sembolik bağlantıları oluştur (yalnızca macOS/Linux)",
                           "Create safe symbolic links (macOS/Linux only)"),
    "set.note": ("Yol güvenliği (Zip Slip, mutlak yollar, '..') her zaman açıktır ve "
                 "kapatılamaz.",
                 "Path safety (Zip Slip, absolute paths, '..') is always on and cannot "
                 "be disabled."),
    "set.general": ("Genel", "General"),
    "set.restart": ("Dil değişikliği yeniden başlatınca tam uygulanır.",
                    "Language change fully applies after restart."),
    "about.text": ("<h2>{app} {ver}</h2><p>{tag}</p>"
                   "<p>MIT lisanslı özgür yazılım. WinRAR ile hiçbir bağlantısı yoktur; "
                   "onun kodunu, adını veya görsellerini kullanmaz.</p>"
                   "<p>Kendi biçimi: CHZ (.chz) — açık, belgeli, AES-256 şifreli.</p>"
                   "<p>Desteklenen biçimler: ZIP, 7Z, TAR, TAR.GZ, TAR.BZ2, TAR.XZ, GZ, "
                   "BZ2, XZ (oluşturma ve açma), RAR (yalnızca açma, gömülü 7-Zip ile).</p>",
                   "<h2>{app} {ver}</h2><p>{tag}</p>"
                   "<p>Free software under the MIT license. Not affiliated with WinRAR; it "
                   "uses none of its code, name or artwork.</p>"
                   "<p>Native format: CHZ (.chz) — open, documented, AES-256 encrypted.</p>"
                   "<p>Formats: ZIP, 7Z, TAR, TAR.GZ, TAR.BZ2, TAR.XZ, GZ, BZ2, XZ (create "
                   "and extract), RAR (extract only, via bundled 7-Zip).</p>"),
    "drop.hint": ("Dosyaları buraya sürükleyin veya bir arşiv açın",
                  "Drag files here or open an archive"),
    "filter.archives": ("Arşivler", "Archives"),
    "filter.all": ("Tüm dosyalar", "All files"),
}


def detect_language() -> str:
    for var in ("CHESTZIP_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var)
        if v:
            return "tr" if v.lower().startswith("tr") else "en"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    return "tr" if loc.lower().startswith("tr") else "en"


def set_language(lang: str) -> None:
    global _LANG
    _LANG = "en" if lang == "en" else "tr"


def get_language() -> str:
    return _LANG


def t(key: str, **kwargs) -> str:
    pair = STRINGS.get(key)
    if pair is None:
        return key
    text = pair[0] if _LANG == "tr" else pair[1]
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            return text
    return text
