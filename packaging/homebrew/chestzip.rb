cask "chestzip" do
  version "1.1.0"
  sha256 "5ba72078dd6ae07162b1c463cdc3f0326eb2926c00643b6881cf178b6eb1a35d"

  url "https://github.com/mesutozansoftware/chestzip/releases/download/v#{version}/ChestZip-#{version}-macos-arm64.zip"
  name "ChestZip"
  desc "Open-source archive manager with zip bomb protection"
  homepage "https://github.com/mesutozansoftware/chestzip"

  depends_on arch: :arm64
  depends_on macos: :monterey

  app "ChestZip.app"
  binary "#{appdir}/ChestZip.app/Contents/MacOS/chestzip"

  # Uygulama henüz Apple tarafından imzalanmadı (notarize edilmedi). Karantina
  # işareti paketin içindeki yüzlerce kütüphaneye de konduğu için macOS
  # uygulamayı başlatırken takılıyor; işaret yalnızca ChestZip.app'ten kaldırılır.
  postflight_steps do
    run "/usr/bin/xattr",
        args:           ["-dr", "com.apple.quarantine", "{{appdir}}/ChestZip.app"],
        writable_paths: ["ChestZip.app"],
        writable_base:  :appdir
  end

  zap trash: "~/Library/Application Support/ChestZip"
end
