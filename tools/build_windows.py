"""Build the restored game with LLVM, open Win32 headers and the current MSVC CRT.

Requires LLVM-MinGW and Visual Studio 2022 C++ Build Tools with a Windows SDK.
The historical VC6 compiler, libraries and headers are never read.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys

from coff_link import CoffObject
from inspect_crt_archive import members
from source_data import append_label, expose_field
from source_leaf import relocate
from source_initializers import bind_static_callbacks, exclude_automatic_tables
from source_comdat import equivalent_comdat_providers
import match

BASE = pathlib.Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def headers_digest(directory):
    """Content identity independent of where the toolchain was unpacked."""
    records=(p.relative_to(directory).as_posix()+':'+digest(p)+'\n'
             for p in sorted(directory.rglob('*')) if p.is_file())
    return hashlib.sha256(''.join(records).encode('utf-8')).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def toolchain(args):
    prefix=os.environ.get('TITBIT_LLVM')
    compiler=(args.compiler or os.environ.get('TITBIT_CLANG') or
              (str(pathlib.Path(prefix)/'bin/clang++.exe') if prefix else None) or
              shutil.which('clang++.exe'))
    if not compiler or not pathlib.Path(compiler).is_file():
        raise ValueError('Install LLVM-MinGW and set TITBIT_LLVM to its directory, or pass --compiler clang++.exe')
    compiler=pathlib.Path(compiler).resolve()
    mingw=args.mingw_headers or compiler.parent.parent/'i686-w64-mingw32/include'
    if not args.mingw_headers and not (mingw/'windows.h').is_file():mingw=compiler.parent.parent/'include'
    vc=args.vc_tools or os.environ.get('VCToolsInstallDir')
    if not vc:
        candidates=[]
        for program in (os.environ.get('ProgramFiles','C:/Program Files'),os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)')):
            candidates += list(pathlib.Path(program).glob('Microsoft Visual Studio/2022/*/VC/Tools/MSVC/*'))
        if candidates:vc=max(candidates,key=lambda p:tuple(map(int,p.name.split('.'))))
    if not vc:raise ValueError('Install Visual Studio 2022 C++ Build Tools, or pass --vc-tools <VC/Tools/MSVC/version>')
    vc=pathlib.Path(vc).resolve()
    kits=args.windows_sdk or pathlib.Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Windows Kits/10'
    kits=kits.resolve()
    versions=[p.name for p in (kits/'Lib').glob('*') if (p/'ucrt/x86/libucrt.lib').is_file()]
    version=args.sdk_version or (max(versions,key=lambda s:tuple(map(int,s.split('.')))) if versions else None)
    if not version:raise ValueError('Install the Windows SDK C++ libraries, or pass --windows-sdk <Windows Kits/10>')
    sdk=kits/'Lib'/version
    tools=vc/'bin/Hostx64/x86'
    missing=[str(p) for p in [mingw/'windows.h',tools/'link.exe',tools/'lib.exe',tools/'cvtres.exe',tools/'ml.exe',
                              vc/'lib/x86/libcmt.lib',vc/'lib/x86/libvcruntime.lib',sdk/'ucrt/x86/libucrt.lib'] if not p.is_file()]
    if missing:raise ValueError('Incomplete modern Windows toolchain: '+', '.join(missing))
    resource=pathlib.Path(subprocess.check_output([str(compiler),'-print-resource-dir'],
                                                 encoding='utf-8').strip())/'include'
    return compiler,mingw.resolve(),vc,sdk,tools,resource


def aliases_object(path, aliases):
    targets = sorted(set(aliases.values()))
    indices = {name:i for i,name in enumerate(targets)}
    strings, symbols = bytearray(b'\0'*4), bytearray()
    def symbol(name, storage, aux):
        raw=name.encode('ascii')
        if len(raw)>8:
            field=struct.pack('<II',0,len(strings)); strings.extend(raw+b'\0')
        else:
            field=raw.ljust(8,b'\0')
        return struct.pack('<8sIhHBB',field,0,0,0,storage,aux)
    for name in targets: symbols.extend(symbol(name,2,0))
    for name,target in sorted(aliases.items()):
        symbols.extend(symbol(name,105,1)); symbols.extend(struct.pack('<II10x',indices[target],3))
    struct.pack_into('<I',strings,0,len(strings))
    path.write_bytes(struct.pack('<HHIIIHH',0x14c,0,0,20,len(symbols)//18,0,0)+symbols+strings)


def library_symbols(path):
    result=set()
    for _,data in members(path.read_bytes()):
        if data[:4]==b'\0\0\xff\xff':
            raw=data[20:].split(b'\0')[0].decode('ascii')
            result.update((raw,'__imp_'+raw)); continue
        try:
            obj=CoffObject(path,data=data)
        except (ValueError,KeyError,struct.error,IndexError):
            continue
        result.update(s['name'] for s in obj.symbols.values()
                      if s['storage']==2 and (s['section']>0 or s['value']>0))
    return result


def main(default_compat=True):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compat',action='store_true',default=default_compat)
    parser.add_argument('--original',action='store_true')
    parser.add_argument('--out',type=pathlib.Path)
    parser.add_argument('--check',action='store_true',help='validate compiler and all public source inputs only')
    parser.add_argument('--fresh',action='store_true',help='compile every source instead of reusing hash-checked compiler objects')
    parser.add_argument('--compiler',type=pathlib.Path)
    parser.add_argument('--mingw-headers',type=pathlib.Path)
    parser.add_argument('--vc-tools',type=pathlib.Path)
    parser.add_argument('--windows-sdk',type=pathlib.Path)
    parser.add_argument('--sdk-version')
    parser.add_argument('--test-runtime',action='store_true',help='Also run the source ABI/container/stdio regression tests as a console process')
    args=parser.parse_args()
    compat=args.compat and not args.original
    compiler,mingw,vc,sdk,tools,resource_headers=toolchain(args)
    config=read(BASE/'config/source-build.json')
    out=(args.out or BASE/'build'/('modern-portable' if compat else 'original-portable')).resolve()
    out.mkdir(parents=True,exist_ok=True)
    objdir=out/'obj';objdir.mkdir(exist_ok=True)
    env=os.environ.copy()
    env['PATH']=str(tools)+os.pathsep+str(compiler.parent)+os.pathsep+env.get('PATH','')
    env.pop('INCLUDE',None)
    env.pop('LIB',None)
    def run(command,log,cwd=BASE):
        result=subprocess.run(command,cwd=cwd,env=env,capture_output=True)
        log.write_bytes(result.stdout+result.stderr)
        if result.returncode:
            print(log.read_text(encoding='utf-8',errors='replace')[-12000:],flush=True)
            raise RuntimeError('Command failed; see '+str(log))
    def response(tool,name,arguments):
        rsp=out/(name+'.rsp')
        def short(arg):
            for root in (BASE,out,sdk,vc): arg=str(arg).replace(str(root),match.short_path(root))
            return arg
        rsp.write_text('\n'.join('"'+short(a)+'"' for a in arguments)+'\n',encoding='ascii')
        run([str(tool),'@'+match.short_path(rsp)],out/(name+'.log'))
    units=list(config['recipes'])
    units=[row for row in units if not row['source'].endswith(('/00498de0-dinput_thunk.asm','/data/cxx_startup.c'))]
    # Authored, compiler-proved storage of the game's shared template guard.
    # A weak alias to VC6 COMMON would otherwise become image-base + sizeof(byte).
    units.append({'source':'src/lanes/codex/data/template_guards.asm','flags':['/coff'],
                  'includes':[],'symbolAddresses':{},'priority':0})
    units += [{'source':source,'flags':[],'includes':[],'symbolAddresses':{},'priority':0} for source in
              ('portable/src/windows_runtime.cpp','linux-port/src/linux_runtime/missing_members.cpp',
               'linux-port/src/linux_runtime/lane_string_members.cpp')]
    if compat:
        units += [{'source':p.relative_to(BASE).as_posix(),'flags':['/O2','/G5','/Gy','/Zl','/GR-'],
                   'includes':[],'symbolAddresses':{},'priority':0}
                  for p in sorted((BASE/'src/compat').glob('compat_*.cpp'))]+[
                    {'source':'src/compat/source_entry.cpp','flags':['/O2','/G5','/Gy','/Zl','/GR-'],
                     'includes':[],'symbolAddresses':{},'priority':0}]
    libs=[sdk/'um/x86'/name for name in config['importLibraries'] if name.upper()!='DINPUT.LIB']
    libs += [vc/'lib/x86'/name for name in ('libcmt.lib','libvcruntime.lib','legacy_stdio_definitions.lib','legacy_stdio_wide_specifiers.lib')]
    libs += [sdk/'ucrt/x86/libucrt.lib']
    missing=[str(BASE/r['source']) for r in units if not (BASE/r['source']).is_file()]
    missing += [str(p) for p in libs if not p.is_file()]
    if missing: raise FileNotFoundError('Missing build inputs: '+'; '.join(missing))
    if args.check:
        print(json.dumps({'sourceUnits':len(units),'compiler':str(compiler),'msvc':str(vc),'windowsSDK':str(sdk),
                          'mingwHeaders':str(mingw),'sourcesPresent':True,'requiresVC6':False},indent=2));return 0
    # Keep immutable compiler output apart from objects whose COFF visibility is adapted for LINK.
    rawdir=out/'compiler-obj';rawdir.mkdir(exist_ok=True)
    inputs=[p for root in (BASE/'src',BASE/'third_party',BASE/'portable',BASE/'linux-port/src/linux_runtime',BASE/'linux-port/src/seer',mingw,resource_headers)
            for p in root.rglob('*') if p.is_file()]
    inputs += [compiler,tools/'ml.exe',BASE/'tools/source_leaf.py',BASE/'config/source-build.json']
    fingerprint=hashlib.sha256(''.join(str(p)+digest(p) for p in sorted(inputs)).encode('utf-8')).hexdigest()
    cachepath=out/'compiler-cache.json'
    cache=read(cachepath) if cachepath.exists() and not args.fresh else {}
    if cache.get('fingerprint')!=fingerprint:cache={'fingerprint':fingerprint,'objects':{}}
    compiled=[]
    for number,row in enumerate(units):
        src=BASE/row['source']; actual=src
        if row['source'].startswith('src/seer/') and src.suffix.lower()=='.c':
            # Shared, tested Clang spelling repairs; the optional VC6 build
            # continues to compile the untouched historical source spelling.
            actual=BASE/'linux-port'/row['source']
        obj=objdir/('%03d_%s.obj'%(number,src.stem))
        if row['source']=='src/native/game_audio.cpp':
            text=src.read_text(encoding='utf-8')
            actual=out/'generated/game_audio.cpp';actual.parent.mkdir(exist_ok=True)
            actual.write_text(text.replace('ActiveSoundEntry* active_sounds;\nint active_sound_count;',
                'extern ActiveSoundEntry* active_sounds;\nextern int active_sound_count;'),encoding='utf-8')
        if row.get('relocatableLeaf'):
            actual=out/'generated'/src.name;actual.parent.mkdir(exist_ok=True)
            actual.write_text(relocate(src.read_text(encoding='utf-8'),config['imageMetadata']['dataRanges'])[0],encoding='utf-8')
        asm=src.suffix.lower()=='.asm'
        raw=rawdir/obj.name
        # The compiler runs in the source's folder; a relative name keeps __FILE__ (SeeR
        # error strings) independent of where the repository is checked out.
        if asm:
            command=[str(tools/'ml.exe'),'/nologo','/c','/coff','/Fo'+str(raw),os.path.relpath(actual,src.parent)]
        else:
            command=[str(compiler),'-target','i686-pc-windows-msvc','-fms-extensions','-fms-compatibility',
                     '-fms-compatibility-version=19.44','-fgnuc-version=4.2.1','-fdeclspec','-fdelayed-template-parsing',
                     '-nostdinc','-DTITBIT_SOURCE_LINK','-DTITBIT_PORTABLE_HEADERS','-DTITBIT_WINDOWS_UCRT',
                     '-D_USE_32BIT_TIME_T','-D__MINGW32__','-D__i386__','-D_X86_',
                     '-O2','-fno-strict-aliasing','-fno-omit-frame-pointer','-ffunction-sections','-fdata-sections',
                     '-Wno-ignored-attributes','-Wno-pragma-pack','-Wno-microsoft-cast','-Wno-macro-redefined',
                     '-Wno-implicit-function-declaration','-ferror-limit=12','-c']
            if src.suffix.lower()=='.c':command+=['-x','c','-std=gnu89']
            else:command+=['-std=c++98','-fcxx-exceptions','-fexceptions']
            if compat:command+=['-DTITBIT_COMPAT']
            for flag in row.get('flags',[]):
                if flag.startswith('/D') and flag!='/Dfor=if (0) ; else for':command+=['-D'+flag[2:]]
                elif flag=='/Zp4':command+=['-fpack-struct=4']
                elif flag=='/Od':command+=['-O0']
            folders=[actual.parent,src.parent,BASE/'src/lanes/include']+[BASE/inc for inc in row['includes']]
            if src.name=='dom_parser.cpp':folders += [BASE/'src/lanes/engine41/cpxml43/xmlincl',BASE/'src/lanes/engine41/cpxml43/xmlincl/SAX']
            folders += [BASE/'portable/include/win32',BASE/'portable/include/cxx',BASE/'portable/include/crt',resource_headers,mingw]
            for folder in folders:command+=['-I',str(folder)]
            command+=['-o',str(raw),os.path.relpath(actual,src.parent)]
        previous=cache['objects'].get(row['source'],{})
        if previous.get('command')!=command or not raw.exists() or previous.get('sha256')!=digest(raw):
            run(command,obj.with_suffix('.log'),src.parent)
            cache['objects'][row['source']]={'command':command,'sha256':digest(raw)}
            cachepath.write_text(json.dumps(cache),encoding='utf-8')
        shutil.copy2(raw,obj)
        compiled.append({**row,'object':str(obj),'command':command,'sourceSha256':digest(src),
                         'actualSource':(actual.relative_to(BASE) if actual.is_relative_to(BASE) else actual).as_posix(),
                         'actualSourceSha256':digest(actual),
                         'objectSha256':digest(obj)})
        if (number+1)%25==0:print('compiled',number+1,'/',len(units),flush=True)
    compiled=[r for r in compiled if not r['source'].endswith('/00498de0-dinput_thunk.asm')]
    bindings={k:int(v,16) for k,v in config['bindings'].items()}
    match.IMPORTS.update(config['imageMetadata']['imports'])
    def address(name,local=None):
        merged=bindings.copy()
        for key,value in (local or {}).items():
            merged[match.UNIT+':'+key]=int(value,16) if isinstance(value,str) else value
        return match.address_of(name,merged)
    # Preserve the source-owned game callback order; the current CRT owns startup.
    initializers={}; initializer_order=set(config['initializerOrder']);automatic_initializers=0
    layout=read(BASE/'src/lanes/codex/link_units.json')
    definitions=set();candidates=collections.defaultdict(list);undefined=collections.defaultdict(set)
    objects={r['object']:CoffObject(r['object']) for r in compiled}
    for row in compiled:
        src=BASE/row['source'];obj=objects[row['object']]
        match.UNIT=src.stem
        local=dict(row.get('symbolAddresses',{}))
        sidecar=src.with_suffix('.bindings.json')
        spec=read(sidecar) if sidecar.exists() else {}
        local.update(spec.get('bindings',{}))
        for name in spec.get('unboundSymbols',[]): local[name]=None
        static=layout['staticInitializers'].get('decompilation/'+row['source'])
        if static:local.update({name:int(field['address'],16) for name,field in static.items()})
        # Export independently identified per-TU static callbacks and data names.
        for symbol in list(obj.symbols.values()):
            a=address(symbol['name'],local)
            section=obj.sections.get(symbol['section'])
            if symbol['storage'] in (2,3) and section and section['flags']&0x20 and a in initializer_order and a not in initializers:
                label='_public_initializer_%08x'%a
                obj=append_label(obj,label,symbol['section'],symbol['value'],symbol_type=0x20)
                initializers.setdefault(a,label)
        # Clang can combine several source constructors in one callback.
        # Retain its actual registration/destruction tables; VC6's per-field
        # initializer identities are not imposed on a different compiler.
        automatic_initializers += sum(len(section['relocations']) for section in obj.sections.values()
                                      if section['name']=='.CRT$XCU')
        data=bytearray(obj.data);offset=struct.unpack_from('<I',data,8)[0]
        for symbol in obj.symbols.values():
            sec=obj.sections.get(symbol['section'])
            if (symbol['storage']==3 and sec and not sec['flags']&0x20 and not symbol['type']&0x20
                    and ('@?1?' in symbol['name'] or src.parent.name=='data') and symbol['name'] in local):
                data[offset+18*symbol['index']+16]=2
        pathlib.Path(row['object']).write_bytes(data);obj=CoffObject(row['object']);objects[row['object']]=obj
        for sym in obj.symbols.values():
            if sym['storage']!=2:continue
            a=address(sym['name'],local)
            if sym['section']>0 or sym['value']>0:
                definitions.add(sym['name'])
                if a is not None:
                    candidates[a].append((row['priority'],sym['name']))
            elif a is not None:undefined[sym['name']].add(a)
        row['_fieldSpec']=spec
    # Existing typed field locators prove offsets within actual source storage.
    for row in compiled:
        for name,spec in row.pop('_fieldSpec').get('fieldAliases',{}).items():
            owners=[r for r in compiled if spec['owner'] in objects[r['object']].by_name
                    and objects[r['object']].by_name[spec['owner']]['section']>0]
            if len(owners)!=1:raise ValueError('Missing field owner '+spec['owner'])
            owner=owners[0];obj,proof=expose_field(objects[owner['object']],objects[row['object']],name,spec,
                                                  address(spec['owner']),address(name))
            pathlib.Path(owner['object']).write_bytes(obj.data);objects[owner['object']]=obj
            definitions.add(name)
            a=address(name)
            if a is not None:candidates[a].append((owner['priority'],name))
    # Clang emits the inlined string assignment and its explicit out-of-line
    # provider as different COMDAT policies. Share a provider only after the
    # existing strict byte-and-relocation equality check proves identity.
    comdat_proofs=[]
    for name in [*layout['identicalComdatProviders'],'?Assign@ObservedString@@QAEAAV1@PBD@Z']:
        for path,(obj,proof) in equivalent_comdat_providers(list(objects.values()),name).items():
            pathlib.Path(path).write_bytes(obj.data);objects[path]=obj
            comdat_proofs.append(proof)
    runtime_symbols=set()
    match.UNIT=''
    for lib in libs:
        symbols=library_symbols(lib);runtime_symbols.update(symbols)
        for name in symbols:
            a=address(name)
            if a is not None:candidates[a].append((-10,name))
    for name,a in config['imageMetadata']['imports'].items():
        for symbol in runtime_symbols:
            if symbol.startswith('__imp_') and symbol[len('__imp_'):].lstrip('_@').split('@')[0]==name:
                candidates[a].append((-10,symbol))
    aliases={}
    for name,addresses in undefined.items():
        if name in definitions or name in runtime_symbols or len(addresses)!=1:continue
        choices=candidates.get(next(iter(addresses)),[])
        if choices:
            target=min(choices)[1]
            if target!=name:aliases[name]=target
    for record in config['aliases']:
        if record['alias'] not in definitions and record['alias'] not in runtime_symbols:
            aliases.setdefault(record['alias'],record['provider'])
    aliases['_g_00500ef0']='_titbit_empty_text'
    commons={s['name'] for obj in objects.values() for s in obj.symbols.values()
             if s['storage']==2 and s['section']==0 and s['value']>0}
    section_names={s['name'] for obj in objects.values() for s in obj.symbols.values()
                   if s['storage']==2 and s['section']>0}
    invalid=set(aliases.values()) & (commons-section_names)
    if invalid:raise ValueError('Weak alias to COMMON has no source section owner: '+', '.join(sorted(invalid)))
    aliases_dir=out/'aliases';aliases_dir.mkdir(exist_ok=True)
    alias_members=[]
    for i,(name,target) in enumerate(sorted(aliases.items())):
        path=aliases_dir/('%04d.obj'%i);aliases_object(path,{name:target});alias_members.append(str(path))
    # The modern CRT invokes the ordered restored game list after its own setup.
    init=out/'generated/game_initializers.cpp';init.parent.mkdir(exist_ok=True)
    labels=['Script_CXX_Initializer_00406970','Script_CXX_Initializer_00413f90',
            'InitializeTextureCache','InitializeResourceCache','FUN_00421580','FUN_004215d0','FUN_00427d70','FUN_004298d0']
    init.write_text('extern "C" {\n'+
        '\n'.join('void __cdecl '+name+'(void);' for name in labels if not name.startswith('Initialize'))+'\n}\n'+
        '\n'.join('void __cdecl '+name+'(void);' for name in labels if name.startswith('Initialize'))+
        '\nstatic void __cdecl initialize_pod_globals() {\n'+
        '\n'.join(' '+name+'();' for name in labels)+'\n}\n'+
        '\n#pragma data_seg(".CRT$XCV")\nextern "C" void (__cdecl *public_game_initializers[])(void) = {initialize_pod_globals};\n',encoding='ascii')
    init_obj=objdir/'game_initializers.obj'
    run([str(compiler),'-target','i686-pc-windows-msvc','-c','-O2','-o',str(init_obj),str(init)],out/'initializers.log')
    response(tools/'lib.exe','sources',['/nologo','/OUT:'+str(out/'sources.lib'),*[r['object'] for r in compiled]])
    response(tools/'lib.exe','aliases',['/nologo','/OUT:'+str(out/'aliases.lib'),*alias_members])
    from rc_compile import compile_rc
    from project_icon import write_icon
    res=out/'game.res';resource=out/'game_resources.obj'
    # Keep resource IDs/dialogs, with our own artwork rather than disc ICOs.
    resources=out/'generated/resources';resources.mkdir(parents=True,exist_ok=True)
    write_icon(resources/'titbit-modern.ico')
    text=(BASE/'src/lanes/codex/resources/titbit.rc').read_text(encoding='utf-8')
    text=text.replace('icon_202_1049.ico','titbit-modern.ico').replace('icon_128_1033.ico','titbit-modern.ico')
    from project_version import versioninfo_rc
    exe=out/('TitbitModern.exe' if compat else 'titbit.exe')
    # The disc EXE's VERSIONINFO names VZlab; an unofficial rebuild must name this project.
    cut=text.rindex('LANGUAGE',0,text.index('1 VERSIONINFO'))
    text=text[:cut]+versioninfo_rc(exe.name,'Nuclear Titbit (rebuilt from restored sources)')
    (resources/'titbit.rc').write_text(text,encoding='utf-8')
    res.write_bytes(compile_rc(resources/'titbit.rc'))  # same bytes as Windows SDK rc.exe
    run([str(tools/'cvtres.exe'),'/NOLOGO','/MACHINE:IX86','/OUT:'+str(resource),str(res)],out/'cvtres.log')
    response(tools/'link.exe','link',['/nologo','/Brepro','/NODEFAULTLIB','/MACHINE:IX86','/SUBSYSTEM:WINDOWS,6.0',
        '/ENTRY:'+('SourceCompatStartup' if compat else 'WinMainCRTStartup'),'/INCREMENTAL:NO','/OPT:REF',
        '/INCLUDE:_public_game_initializers','/OUT:'+str(exe),'/MAP:'+str(exe.with_suffix('.map')),
        str(resource),str(init_obj),*[r['object'] for r in compiled if r['source'].endswith('/template_guards.asm')],
        str(out/'sources.lib'),str(out/'aliases.lib'),*map(str,libs)])
    if compat:
        launch=BASE/'src/compat/launcher.cpp';launch_obj=objdir/'launcher.obj'
        launch_flags=[str(compiler),'-target','i686-pc-windows-msvc','-fms-extensions','-fms-compatibility',
                      '-fgnuc-version=4.2.1','-D__MINGW32__','-D__i386__','-D_X86_',
                      '-DTITBIT_WINDOWS_UCRT','-nostdinc','-c','-O2','-Wno-pragma-pack','-Wno-ignored-attributes',
                      '-Wno-macro-redefined','-Wno-implicit-function-declaration']
        for folder in (BASE/'portable/include/win32',BASE/'portable/include/crt',resource_headers,mingw):launch_flags+=['-I',str(folder)]
        run([*launch_flags,'-o',str(launch_obj),str(launch)],out/'launcher-compile.log')
        settings_rc=resources/'settings.rc'
        settings_rc.write_text('LANGUAGE 0x9, 0x1\n\n1 ICON "titbit-modern.ico"\n\n'+versioninfo_rc('TitbitSettings.exe','Titbit display settings and launcher'),encoding='utf-8')
        (out/'settings.res').write_bytes(compile_rc(settings_rc))
        run([str(tools/'cvtres.exe'),'/NOLOGO','/MACHINE:IX86','/OUT:'+str(out/'settings_resources.obj'),str(out/'settings.res')],out/'settings-cvtres.log')
        response(tools/'link.exe','launcher',['/nologo','/Brepro','/SUBSYSTEM:WINDOWS','/ENTRY:WinMainCRTStartup','/NODEFAULTLIB',
                 '/OUT:'+str(out/'TitbitSettings.exe'),str(launch_obj),str(out/'settings_resources.obj'),
                 *[str(sdk/'um/x86'/x) for x in ('KERNEL32.LIB','USER32.LIB','GDI32.LIB')],
                 *[str(vc/'lib/x86'/x) for x in ('libcmt.lib','libvcruntime.lib','legacy_stdio_definitions.lib','legacy_stdio_wide_specifiers.lib')],str(sdk/'ucrt/x86/libucrt.lib')])
        (out/'titbit_compat.ini').write_text('[compat]\ndisplay=fullscreen\nresolution=1024x768\naspect=fit\nsetup=modern\ncd=folder\nvideo=auto\nreplay=off\n',encoding='ascii')
    # /Brepro fixes linker-generated identities; use the source epoch for the
    # human-readable PE timestamp as well.
    stamp=source_date()
    for built in [exe]+([out/'TitbitSettings.exe'] if compat else []):
        data=bytearray(built.read_bytes());header=struct.unpack_from('<I',data,0x3c)[0]
        struct.pack_into('<I',data,header+8,stamp);built.write_bytes(bytes(data))
    manifest={'linked':True,'compat':compat,'linkExit':0,'sourceUnits':len(compiled),'executable':str(exe),
              'sha256':digest(exe),'objects':[{k:v for k,v in r.items() if not k.startswith('_')} for r in compiled],
              'runtime':'current MSVC libcmt + libvcruntime + Windows SDK libucrt','requiresVC6':False,
              'compiler':str(compiler),'msvc':str(vc),'windowsSDK':str(sdk),'mingwHeaders':str(mingw),
              'libraries':[{'name':p.name,'sha256':digest(p)} for p in libs],
              # what someone else needs to get the same bytes (tools/verify_release.py)
              'sourceDateEpoch':stamp,
              'tools':{p.name:digest(p) for p in (compiler,tools/'link.exe',tools/'lib.exe',tools/'cvtres.exe',tools/'ml.exe')},
              'headers':{'mingw-w64':headers_digest(mingw),'clang-resource':headers_digest(resource_headers)},
              'settingsSha256':digest(out/'TitbitSettings.exe') if compat else None,
              'gameInitializers':automatic_initializers+len(labels),'automaticInitializers':automatic_initializers,
              'explicitPODInitializers':len(labels),'aliases':aliases,'identicalComdatProofs':comdat_proofs}
    (out/'build-info.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('LINK OK:',exe,'SHA256',digest(exe),flush=True)
    if args.test_runtime:
        runtime_out=out/'runtime-test'
        run([sys.executable,str(BASE/'tools/check_windows_runtime.py'),'--compiler',str(compiler),
             '--mingw-headers',str(mingw),'--vc-tools',str(vc),'--windows-sdk',str(sdk.parents[1]),
             '--sdk-version',sdk.name,'--out',str(runtime_out)],out/'runtime-test.log')
        manifest['runtimeTests']=read(runtime_out/'result.json')
        (out/'build-info.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print('Windows source ABI/container/stdio runtime tests: OK',flush=True)
    return 0


def source_date():
    """SOURCE_DATE_EPOCH, else the commit time, else 0: same sources, same EXE."""
    if os.environ.get('SOURCE_DATE_EPOCH'):
        return int(os.environ['SOURCE_DATE_EPOCH'])
    try:
        return int(subprocess.check_output(['git','-C',str(BASE),'log','-1','--format=%ct'],
                                           stderr=subprocess.DEVNULL).strip() or 0)
    except (OSError,subprocess.CalledProcessError,ValueError):
        return 0


if __name__=='__main__':
    sys.exit(main())
