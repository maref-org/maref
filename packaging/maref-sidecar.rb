# Homebrew formula for the MAREF governance Sidecar binary.
#
# Install (once a tap is published):
#   brew install maref-org/tap/maref-sidecar
#
# NOTE: version + sha256 are filled in at the first tagged release.
#   Version  -> the v* git tag (e.g. 0.42.0)
#   sha256   -> `shasum -a 256 dist/maref-sidecar-darwin-arm64`
class MarefSidecar < Formula
  desc "MAREF Sidecar — agent governance runtime (governance FSM, audit, MCP bridge)"
  homepage "https://github.com/maref-org/maref"
  version "0.43.0"
  license "Apache-2.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/maref-org/maref/releases/download/v#{version}/maref-sidecar-darwin-arm64"
      sha256 "97c1ce5f45f4823fd22c42dc0ab32ed968ea36478b9d60f307664776d20fa4fc"
    else
      url "https://github.com/maref-org/maref/releases/download/v#{version}/maref-sidecar-darwin-x86_64"
      sha256 "REPLACE_WITH_X86_64_SHA256"
    end
  end

  on_linux do
    url "https://github.com/maref-org/maref/releases/download/v#{version}/maref-sidecar-linux-x86_64"
    sha256 "REPLACE_WITH_LINUX_SHA256"
  end

  def install
    bin.install "maref-sidecar"
  end

  test do
    system "#{bin}/maref-sidecar", "--help"
  end
end
