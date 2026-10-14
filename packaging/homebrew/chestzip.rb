cask "chestzip" do
  version "1.0.0"
  sha256 "f4ea047386cd996f1435e33f09c9ae5fdf247f4104ea285465dc17e2e1458048"

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
  postflight do
    system_command "/usr/bin/xattr",
                   args: ["-dr", "com.apple.quarantine", "#{appdir}/ChestZip.app"]
  end

  zap trash: "~/Library/Application Support/ChestZip"
end
