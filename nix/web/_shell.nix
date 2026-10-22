{
  lib,
  pkgs,
  toolchain,
  win32Headers,
}:
let
  inherit (pkgs) emscripten;
  resourceDir = "${lib.getLib toolchain.clang-unwrapped}/lib/clang/18";
  llvmConfig = "${lib.getDev toolchain.llvm}/bin/llvm-config";
  doctor = pkgs.writeShellApplication {
    name = "titbit-web-doctor";
    runtimeInputs = [
      emscripten
      pkgs.nodejs
      pkgs.coreutils
    ];
    text = ''
      emcc --version
      ${llvmConfig} --version
      node --version
      temporary=$(mktemp -d -t titbit-web-doctor.XXXXXXXX)
      trap 'rm -rf "$temporary"' EXIT
      cat > "$temporary/check.c" <<'SOURCE'
      #include <stdio.h>
      int main(void) {
        puts("Titbit: Emscripten + libc + WebAssembly + Node.js OK");
        return 0;
      }
      SOURCE
      emcc "$temporary/check.c" -sENVIRONMENT=node -o "$temporary/check.js"
      node "$temporary/check.js"
    '';
  };
in
pkgs.mkShellNoCC {
  packages = [
    emscripten
    toolchain.clang-unwrapped
    toolchain.llvm
    (lib.getDev toolchain.llvm)
    (lib.getBin toolchain.lld)
    pkgs.binaryen
    pkgs.nodejs
    pkgs.python3
    pkgs.cmake
    pkgs.ninja
    pkgs.gnumake
    pkgs.pkg-config
    pkgs.autoconf
    pkgs.automake
    pkgs.libtool
    pkgs.curl
    pkgs.aria2
    pkgs.git
    pkgs.patch
    pkgs.coreutils
    pkgs.ffmpeg_6
    doctor
  ];

  # Keep the MS-ABI frontend on LLVM 18. emcc uses its own matching LLVM,
  # independently of the Clang executable exposed in this shell's PATH.
  TITBIT_CLANG = "${toolchain.clang-unwrapped}/bin/clang++";
  TITBIT_CLANG_RESOURCE_DIR = resourceDir;
  TITBIT_LLVM_CONFIG = llvmConfig;
  TITBIT_NATIVE_CXX = "${toolchain.clang}/bin/clang++";
  TITBIT_WIN32_HEADERS = "${win32Headers}/include";
  TITBIT_PLAYWRIGHT_MODULE = "${pkgs.playwright-driver}/index.mjs";
  PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers-chromium}";
  PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";

  shellHook = ''
    # Emscripten ports and additional libc variants must not write to /nix/store.
    # A store-path key isolates caches when Nix changes the SDK or its LLVM.
    export EM_CACHE="''${EM_CACHE:-''${XDG_CACHE_HOME:-$HOME/.cache}/titbit/${builtins.baseNameOf (toString emscripten)}}"
    mkdir -p "$EM_CACHE"
    if [ ! -d "$EM_CACHE/sysroot" ]; then
      cp -R ${emscripten}/share/emscripten/cache/. "$EM_CACHE/"
      chmod -R u+w "$EM_CACHE"
    fi
    echo "Titbit web: Emscripten ${emscripten.version}, LLVM 18. Run titbit-web-doctor to verify."
  '';
}
