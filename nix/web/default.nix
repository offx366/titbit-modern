{ lib, ... }:
{
  perSystem =
    { pkgs, ... }:
    let
      toolchain = pkgs.llvmPackages_18;
      probe = pkgs.callPackage ./_probe.nix {
        src = ../..;
        inherit toolchain;
      };
      objects = pkgs.callPackage ./_objects.nix {
        src = ../..;
        inherit toolchain;
        win32Headers = pkgs.pkgsCross.mingw32.windows.mingw_w64_headers;
      };
      serve = pkgs.writeShellApplication {
        name = "titbit-web-probe";
        runtimeInputs = [ pkgs.python3 ];
        text = ''
          echo "Титбит: техническая проверка WebAssembly (не игровая сборка)."
          echo "Откройте http://127.0.0.1:''${1:-8000}"
          exec python3 -m http.server "''${1:-8000}" --bind 127.0.0.1 \
            --directory ${probe}/share/titbit-web-probe
        '';
      };
    in
    {
      packages = {
        titbit-web-probe = probe;
        titbit-web-objects = objects;
      };
      apps.titbit-web-probe = {
        type = "app";
        program = lib.getExe serve;
        meta.description = "Serve the experimental Titbit Wasm compiler and SeeR probes";
      };
      checks.titbit-web-probe = probe;
      devShells.web = pkgs.callPackage ./_shell.nix {
        inherit toolchain;
        win32Headers = pkgs.pkgsCross.mingw32.windows.mingw_w64_headers;
      };
    };
}
