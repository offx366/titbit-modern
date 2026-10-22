{
  lib,
  stdenvNoCC,
  python3,
  toolchain,
  win32Headers,
  src,
}:
stdenvNoCC.mkDerivation {
  pname = "titbit-web-objects";
  version = lib.trim (builtins.readFile (src + "/VERSION"));
  src = lib.fileset.toSource {
    root = src;
    fileset = lib.fileset.unions [
      (src + "/linux-port/config")
      (src + "/linux-port/src")
      (src + "/linux-port/third_party")
      (lib.fileset.fileFilter (file: file.hasExt "py") (src + "/linux-port/tools"))
      (src + "/linux-port/tools/wasm_varargs.cpp")
      (src + "/linux-port/probes/ms_eh_to_dwarf.py")
      (src + "/linux-port/probes/retarget_ir.py")
      (src + "/portable")
    ];
  };
  nativeBuildInputs = [ python3 ];
  postPatch = ''
    patch -p1 < ${../engine/portable-headers.patch}
  '';
  dontConfigure = true;
  buildPhase = ''
    runHook preBuild
    jobs=$NIX_BUILD_CORES
    if (( jobs > 64 )); then jobs=64; fi
    python3 linux-port/tools/build_wasm_varargs.py \
      --compiler ${toolchain.clang}/bin/clang++ \
      --llvm-config ${lib.getDev toolchain.llvm}/bin/llvm-config \
      --out build/wasm-varargs
    python3 linux-port/tools/compile_ms_ir.py \
      --compiler ${toolchain.clang-unwrapped}/bin/clang++ \
      --resource-dir ${lib.getLib toolchain.clang-unwrapped}/lib/clang/18 \
      --win32-headers ${win32Headers}/include \
      --out linux-port/build/web/ms-ir --with-runtime --jobs "$jobs"
    python3 linux-port/tools/ms_ir_to_wasm.py \
      --compiler ${toolchain.clang-unwrapped}/bin/clang++ --jobs "$jobs" \
      --varargs-lowerer build/wasm-varargs
    runHook postBuild
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/titbit-web-objects"
    cp -r linux-port/build/web/objects "$out/share/titbit-web-objects/"
    cp linux-port/build/web/ms-ir/report.json "$out/share/titbit-web-objects/frontend.json"
    runHook postInstall
  '';
  dontStrip = true;
  meta = {
    description = "Experimental Titbit Wasm object compilation audit; not a linked game";
    license = lib.licenses.unfree;
    platforms = lib.platforms.unix;
  };
}
