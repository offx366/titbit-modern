{
  lib,
  stdenvNoCC,
  python3,
  nodejs,
  toolchain,
  src,
}:
stdenvNoCC.mkDerivation {
  pname = "titbit-web-probe";
  version = lib.trim (builtins.readFile (src + "/VERSION"));
  src = lib.fileset.toSource {
    root = src;
    fileset = lib.fileset.unions [
      (src + "/portable/include/crt")
      (src + "/linux-port/probes/msabi_probe.cpp")
      (src + "/linux-port/probes/msabi_inalloca.cpp")
      (src + "/linux-port/probes/ms_eh_to_dwarf.py")
      (src + "/linux-port/probes/retarget_ir.py")
      (src + "/linux-port/src/native")
      (src + "/linux-port/src/lanes/engine41/quest_state.cpp")
      (src + "/linux-port/src/lanes/engine41/quest_state.h")
      (src + "/linux-port/src/audiere/audiere.h")
      (src + "/linux-port/src/seer")
      (src + "/linux-port/web")
      (src + "/linux-port/tools/build_web_probe.py")
      (src + "/linux-port/tools/ms_ir_to_wasm.py")
      (src + "/linux-port/tools/build_wasm_varargs.py")
      (src + "/linux-port/tools/wasm_varargs.cpp")
      (src + "/linux-port/tools/tests/test_wasm_varargs.py")
    ];
  };
  nativeBuildInputs = [
    python3
    nodejs
  ];
  dontConfigure = true;
  buildPhase = ''
    runHook preBuild
    python3 linux-port/tools/build_wasm_varargs.py \
      --compiler ${toolchain.clang}/bin/clang++ \
      --llvm-config ${lib.getDev toolchain.llvm}/bin/llvm-config \
      --out build/wasm-varargs
    python3 linux-port/tools/build_web_probe.py \
      --compiler ${toolchain.clang-unwrapped}/bin/clang++ \
      --resource-dir ${lib.getLib toolchain.clang-unwrapped}/lib/clang/18 \
      --linker ${lib.getBin toolchain.lld}/bin/wasm-ld \
      --varargs-lowerer build/wasm-varargs \
      --out build/web-probe
    runHook postBuild
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    TITBIT_WASM_VARARGS="$PWD/build/wasm-varargs" \
      python3 -m unittest discover -s linux-port/tools/tests -p test_wasm_varargs.py
    node build/web-probe/check.mjs build/web-probe/titbit-probe.wasm
    node build/web-probe/check-save-wasm.mjs build/web-probe/titbit-save-probe.wasm
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/titbit-web-probe"
    cp build/web-probe/{index.html,probe.js,check.mjs,titbit-probe.wasm,build.json} \
      build/web-probe/{titbit-save-probe.wasm,saves.js,save-probe.html,save-probe.js} \
      build/web-probe/{save-checks.html,save-checks.js,check-save-wasm.mjs} \
      "$out/share/titbit-web-probe/"
    runHook postInstall
  '';
  # The output contains a Wasm binary, not native executables to strip.
  dontStrip = true;
  meta = {
    description = "Experimental Titbit WebAssembly ABI, engine geometry and SeeR checks; not a playable game";
    license = lib.licenses.unfree;
    platforms = lib.platforms.unix;
  };
}
