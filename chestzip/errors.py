"""ChestZip genelinde kullanılan hata tipleri."""


class ArchiveError(Exception):
    """Arşiv işlemlerindeki genel hata."""


class UnsupportedFormat(ArchiveError):
    """Dosya tanınan bir arşiv biçiminde değil."""


class UnsupportedOperation(ArchiveError):
    """Bu biçim istenen işlemi desteklemiyor (ör. RAR oluşturma)."""


class PasswordRequired(ArchiveError):
    """Arşiv şifreli ve şifre verilmedi."""


class WrongPassword(ArchiveError):
    """Verilen şifre yanlış."""


class Cancelled(ArchiveError):
    """Kullanıcı işlemi iptal etti."""


class SafetyError(ArchiveError):
    """Güvenlik sınırı aşıldı (zip bombası şüphesi vb.)."""


class UnsafePathError(SafetyError):
    """Arşivdeki yol hedef klasörün dışına çıkmaya çalışıyor (Zip Slip)."""
