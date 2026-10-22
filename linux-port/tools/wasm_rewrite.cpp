// Resolve reconstructed source aliases and preserve their physical MS x86 calls.
// Native LLVM 18 tool; input/output are source-generated Wasm LLVM IR modules.
#include <llvm/IR/Constants.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/InstIterator.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Operator.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/Support/JSON.h>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Support/SourceMgr.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/Support/MathExtras.h>
#include <algorithm>
#include <cstdlib>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>
using namespace llvm;

static void die(const Twine &message) { errs() << "Wasm ABI rewrite: " << message << '\n'; exit(1); }
static std::string encoded(StringRef name) {
    std::string raw;
    for (unsigned char ch : name) {
        if (ch < 32 || ch == '"' || ch == '\\') {
            const char hex[] = "0123456789ABCDEF";
            raw += '\\'; raw += hex[ch >> 4]; raw += hex[ch & 15];
        } else raw += ch;
    }
    if (raw.find_first_of("@?\\") == std::string::npos) return raw;
    std::string result = "titbit_ms_";
    for (unsigned char ch : raw) { const char hex[] = "0123456789abcdef"; result += hex[ch >> 4]; result += hex[ch & 15]; }
    return result;
}
struct Shape { Type *frame = nullptr; Type *byval = nullptr; };
struct Prototype { Function *function; std::vector<Shape> shapes; bool packed = false; };
struct Unit {
    std::unique_ptr<Module> module;
    std::unique_ptr<Module> raw;
    std::string output, source;
    std::map<std::string, Prototype> prototypes;
};
static std::unique_ptr<Module> readModule(StringRef path, LLVMContext &context) {
    SMDiagnostic diagnostic;
    auto module = parseIRFile(path, diagnostic, context);
    if (!module) { diagnostic.print("wasm-rewrite", errs()); exit(1); }
    return module;
}
static Prototype shape(Function &function) {
    Prototype result{&function, {}, function.getName().starts_with("titbit_va_")};
    for (unsigned i = 0; i < function.arg_size(); ++i) {
        Shape param;
        if (function.hasParamAttribute(i, Attribute::InAlloca)) param.frame = function.getParamInAllocaType(i);
        if (function.hasParamAttribute(i, Attribute::ByVal)) param.byval = function.getParamByValType(i);
        result.shapes.push_back(param);
    }
    return result;
}
static uint64_t paramSize(const DataLayout &layout, Type *type, Shape shape) {
    return alignTo(layout.getTypeAllocSize(shape.frame ? shape.frame : shape.byval ? shape.byval : type).getFixedValue(), 4);
}
static uint64_t frameSize(const DataLayout &layout, FunctionType *type, const std::vector<Shape> &shapes) {
    uint64_t bytes = 0;
    for (unsigned i = 0; i < type->getNumParams(); ++i) bytes += paramSize(layout, type->getParamType(i), shapes[i]);
    return bytes;
}
static Function *declareFunction(Module &module, Function &target) {
    if (auto *existing = module.getFunction(target.getName())) return existing;
    auto *result = Function::Create(target.getFunctionType(), GlobalValue::ExternalLinkage,
                                    target.getAddressSpace(), target.getName(), &module);
    result->setAttributes(target.getAttributes());
    result->setCallingConv(target.getCallingConv());
    return result;
}
static Value *convertResult(IRBuilder<> &builder, Value *value, Type *expected) {
    auto *actual = value->getType();
    if (actual == expected) return value;
    if (actual->isIntegerTy() && expected->isPointerTy()) return builder.CreateIntToPtr(value, expected);
    if (actual->isPointerTy() && expected->isIntegerTy()) return builder.CreatePtrToInt(value, expected);
    if (actual->isIntegerTy() && expected->isIntegerTy()) return builder.CreateIntCast(value, expected, true);
    if (actual->isFloatingPointTy() && expected->isFloatingPointTy()) return builder.CreateFPCast(value, expected);
    if (actual->getPrimitiveSizeInBits() == expected->getPrimitiveSizeInBits())
        return builder.CreateBitCast(value, expected);
    die("incompatible scalar result in " + builder.GetInsertBlock()->getParent()->getName());
    return nullptr;
}

static void adaptCall(CallBase *call, Prototype original, Function *target, Prototype actual) {
    bool differs = call->getFunctionType() != target->getFunctionType();
    for (unsigned i = 0; i < std::min(original.shapes.size(), actual.shapes.size()); ++i)
        differs |= original.shapes[i].frame != actual.shapes[i].frame || original.shapes[i].byval != actual.shapes[i].byval;
    if (!differs) return;
    if (!isa<CallInst>(call) && !isa<InvokeInst>(call)) die("callbr is unsupported");
    const auto &layout = call->getModule()->getDataLayout();
    uint64_t from = frameSize(layout, call->getFunctionType(), original.shapes);
    uint64_t to = frameSize(layout, target->getFunctionType(), actual.shapes);
    bool packTrailing = actual.packed && !original.packed;
    if (packTrailing) to -= 4;
    if (to > from) die("callee needs more physical argument bytes: " + target->getName() +
                       " (" + Twine(from) + " -> " + Twine(to) + ") in " + call->getFunction()->getName());
    IRBuilder<> entry(&*call->getFunction()->getEntryBlock().getFirstInsertionPt());
    auto *buffer = entry.CreateAlloca(ArrayType::get(entry.getInt8Ty(), std::max(from, uint64_t(4))), nullptr, "ms.call.frame");
    buffer->setAlignment(Align(4));
    IRBuilder<> builder(call);
    uint64_t offset = 0;
    for (unsigned i = 0; i < call->arg_size(); ++i) {
        auto param = original.shapes[i];
        auto *value = call->getArgOperand(i);
        auto *slot = builder.CreateConstGEP1_32(builder.getInt8Ty(), buffer, offset);
        if (param.frame || param.byval) {
            auto bytes = layout.getTypeAllocSize(param.frame ? param.frame : param.byval).getFixedValue();
            builder.CreateMemCpy(slot, Align(4), value, Align(1), bytes);
        } else builder.CreateAlignedStore(value, slot, Align(4));
        offset += paramSize(layout, value->getType(), param);
    }
    SmallVector<Value *> args;
    offset = 0;
    for (unsigned i = 0; i < target->arg_size(); ++i) {
        auto param = actual.shapes[i];
        auto *type = target->getFunctionType()->getParamType(i);
        auto *slot = builder.CreateConstGEP1_32(builder.getInt8Ty(), buffer, offset);
        if (packTrailing && i + 1 == target->arg_size()) { args.push_back(slot); break; }
        args.push_back(param.frame || param.byval ? slot : builder.CreateAlignedLoad(type, slot, Align(4)));
        offset += paramSize(layout, type, param);
    }
    SmallVector<OperandBundleDef> bundles;
    call->getOperandBundlesAsDefs(bundles);
    CallBase *replacement;
    if (auto *invoke = dyn_cast<InvokeInst>(call)) {
        auto *normal = invoke->getNormalDest();
        if (!call->use_empty() && call->getType() != target->getReturnType()) {
            auto *edge = BasicBlock::Create(call->getContext(), "ms.result", call->getFunction(), normal);
            BranchInst::Create(normal, edge);
            normal->replacePhiUsesWith(call->getParent(), edge);
            normal = edge;
        }
        replacement = builder.CreateInvoke(target->getFunctionType(), target, normal,
                                            invoke->getUnwindDest(), args, bundles);
    } else replacement = builder.CreateCall(target->getFunctionType(), target, args, bundles);
    replacement->setCallingConv(target->getCallingConv());
    replacement->setAttributes(target->getAttributes());
    replacement->setDebugLoc(call->getDebugLoc());
    if (!call->use_empty()) {
        Value *returned = replacement;
        if (target->getReturnType()->isVoidTy()) {
            returned = nullptr;
            for (unsigned i = 0; i < target->arg_size(); ++i)
                if (target->hasParamAttribute(i, Attribute::StructRet)) returned = args[i];
            // MS x86 returns the hidden structure destination in EAX.
            if (!returned || !call->getType()->isPointerTy()) die("used result of void alias: " + target->getName());
        }
        if (isa<InvokeInst>(call) && call->getType() != replacement->getType()) {
            auto *normal = cast<InvokeInst>(replacement)->getNormalDest();
            builder.SetInsertPoint(&*normal->getFirstInsertionPt());
        }
        call->replaceAllUsesWith(convertResult(builder, returned, call->getType()));
    }
    call->eraseFromParent();
}

static void emitDispatcher(StringRef path, LLVMContext &context, StringRef layout,
                           const std::map<std::string, Prototype> &callbacks,
                           const std::map<std::string, Prototype> &prototypes) {
    Module module("typed SeeR callbacks", context);
    module.setTargetTriple("wasm32-unknown-unknown");
    module.setDataLayout(layout);
    IRBuilder<> builder(context);
    auto *signature = FunctionType::get(builder.getVoidTy(),
        {builder.getPtrTy(), builder.getPtrTy(), builder.getPtrTy(), builder.getInt32Ty(), builder.getInt32Ty()}, false);
    auto *dispatch = Function::Create(signature, GlobalValue::ExternalLinkage, "tb_seer_dispatch", module);
    auto *result = dispatch->getArg(0), *pointer = dispatch->getArg(1), *params = dispatch->getArg(2);
    auto *bytes = dispatch->getArg(3), *options = dispatch->getArg(4);
    builder.SetInsertPoint(BasicBlock::Create(context, "entry", dispatch));
    auto error = module.getOrInsertFunction("tb_seer_dispatch_error", builder.getVoidTy(),
        builder.getPtrTy(), builder.getInt32Ty(), builder.getInt32Ty(), builder.getPtrTy());
    for (auto &[name, proto] : callbacks) {
        auto *target = declareFunction(module, *proto.function);
        auto *run = BasicBlock::Create(context, "invoke", dispatch);
        auto *next = BasicBlock::Create(context, "next", dispatch);
        builder.CreateCondBr(builder.CreateICmpEQ(pointer, target), run, next);
        builder.SetInsertPoint(run);
        bool smallStruct = target->getReturnType()->isIntegerTy();
        Value *skip = builder.getInt32(0);
        if (smallStruct) skip = builder.CreateSelect(builder.CreateICmpNE(
            builder.CreateAnd(options, builder.getInt32(7u << 22)), builder.getInt32(0)),
            builder.getInt32(4), builder.getInt32(0));
        uint64_t required = 0;
        unsigned fixed = target->arg_size() - (proto.packed ? 1 : 0);
        for (unsigned i = 0; i < fixed; ++i)
            required += paramSize(module.getDataLayout(), target->getFunctionType()->getParamType(i), proto.shapes[i]);
        auto *bad = BasicBlock::Create(context, "bad.count", dispatch);
        auto *ok = BasicBlock::Create(context, "call", dispatch);
        auto *needed = builder.CreateAdd(builder.getInt32(required), skip);
        builder.CreateCondBr(builder.CreateICmpULT(bytes, needed), bad, ok);
        builder.SetInsertPoint(bad);
        builder.CreateCall(error, {pointer, bytes, needed, builder.CreateGlobalStringPtr(name)});
        builder.CreateUnreachable();
        builder.SetInsertPoint(ok);
        auto *base = builder.CreateGEP(builder.getInt8Ty(), params, skip);
        SmallVector<Value *> args;
        uint64_t offset = 0;
        for (unsigned i = 0; i < target->arg_size(); ++i) {
            auto *slot = builder.CreateConstGEP1_32(builder.getInt8Ty(), base, offset);
            if (proto.packed && i == fixed) { args.push_back(slot); break; }
            auto param = proto.shapes[i];
            auto *type = target->getFunctionType()->getParamType(i);
            args.push_back(param.frame || param.byval ? slot : builder.CreateAlignedLoad(type, slot, Align(4)));
            offset += paramSize(module.getDataLayout(), type, param);
        }
        auto *call = builder.CreateCall(target->getFunctionType(), target, args);
        call->setAttributes(target->getAttributes());
        call->setCallingConv(target->getCallingConv());
        auto *type = target->getReturnType();
        if (type->isFloatingPointTy()) {
            auto *wide = builder.CreateFPCast(call, builder.getDoubleTy());
            auto *asDouble = BasicBlock::Create(context, "double.result", dispatch);
            auto *asWord = BasicBlock::Create(context, "word.result", dispatch);
            builder.CreateCondBr(builder.CreateICmpNE(builder.CreateAnd(options, builder.getInt32(1u << 26)),
                                                    builder.getInt32(0)), asDouble, asWord);
            builder.SetInsertPoint(asDouble);
            builder.CreateAlignedStore(wide, result, Align(4)); builder.CreateRetVoid();
            builder.SetInsertPoint(asWord);
            Value *bits = builder.CreateBitCast(call, type->isFloatTy() ? builder.getInt32Ty() : builder.getInt64Ty());
            if (!type->isFloatTy()) bits = builder.CreateTrunc(bits, builder.getInt32Ty());
            builder.CreateAlignedStore(bits, result, Align(4));
        } else if (!type->isVoidTy()) {
            Value *value = call;
            if (type->isPointerTy()) value = builder.CreatePtrToInt(value, builder.getInt32Ty());
            else if (type->isIntegerTy()) {
                if (type->getIntegerBitWidth() < 32)
                    value = builder.CreateIntCast(value, builder.getInt32Ty(), target->hasRetAttribute(Attribute::SExt));
            } else die("unsupported SeeR return type: " + name);
            Value *destination = result;
            if (smallStruct) {
                auto *structPointer = builder.CreateAlignedLoad(builder.getPtrTy(), params, Align(4));
                destination = builder.CreateSelect(builder.CreateICmpNE(skip, builder.getInt32(0)), structPointer, result);
            }
            builder.CreateAlignedStore(value, destination, Align(4));
        }
        builder.CreateRetVoid();
        builder.SetInsertPoint(next);
    }
    builder.CreateCall(error, {pointer, bytes, builder.getInt32(0), builder.CreateGlobalStringPtr("unknown callback")});
    builder.CreateUnreachable();
    // Recovered DOM views declare deleting destructors as void. MS x86 ignores
    // their EAX result; Wasm requires the actual pointer-returning signature.
    auto *destroyType = FunctionType::get(builder.getVoidTy(),
        {builder.getPtrTy(),builder.getPtrTy(),builder.getInt32Ty()},false);
    auto *destroy = Function::Create(destroyType,GlobalValue::ExternalLinkage,"tb_indirect_destroy",module);
    builder.SetInsertPoint(BasicBlock::Create(context,"entry",destroy));
    for (auto &[name, proto] : prototypes) {
        if (!StringRef(name).starts_with("titbit_ms_3f3f5f47") && !StringRef(name).starts_with("titbit_ms_3f3f5f45")) continue;
        auto *type = proto.function->getFunctionType();
        if (type->getNumParams()!=2 || !type->getParamType(0)->isPointerTy() ||
            !type->getParamType(1)->isIntegerTy(32) || !type->getReturnType()->isPointerTy()) continue;
        auto *target = declareFunction(module,*proto.function);
        auto *run = BasicBlock::Create(context,"destroy",destroy);
        auto *next = BasicBlock::Create(context,"next",destroy);
        builder.CreateCondBr(builder.CreateICmpEQ(destroy->getArg(0),target),run,next);
        builder.SetInsertPoint(run);
        builder.CreateCall(target,{destroy->getArg(1),destroy->getArg(2)});
        builder.CreateRetVoid();builder.SetInsertPoint(next);
    }
    auto *fallbackType=FunctionType::get(builder.getVoidTy(),{builder.getPtrTy(),builder.getInt32Ty()},false);
    builder.CreateCall(fallbackType,destroy->getArg(0),{destroy->getArg(1),destroy->getArg(2)});
    builder.CreateRetVoid();
    if (verifyModule(module, &errs())) die("typed dispatcher verification failed");
    std::error_code errorCode;
    raw_fd_ostream output(path, errorCode);
    if (errorCode) die(errorCode.message());
    module.print(output, nullptr);
    outs() << "Generated " << callbacks.size() << " typed SeeR adapters\n";
}

int main(int argc, char **argv) {
    if (argc != 2) die("Usage: wasm-rewrite plan.json");
    auto buffer = MemoryBuffer::getFile(argv[1]);
    if (!buffer) die("cannot read plan");
    auto parsed = json::parse((*buffer)->getBuffer());
    if (!parsed) die("invalid plan JSON");
    auto *plan = parsed->getAsObject();
    LLVMContext context;
    std::vector<Unit> units;
    for (auto &value : *plan->getArray("rows")) {
        auto *row = value.getAsObject();
        Unit unit;
        unit.source = row->getString("source")->str();
        unit.output = row->getString("out")->str();
        unit.module = readModule(*row->getString("ir"), context);
        unit.raw = readModule(*row->getString("raw"), context);
        for (auto &function : *unit.raw) unit.prototypes.emplace(encoded(function.getName()), shape(function));
        units.push_back(std::move(unit));
    }
    // Wasm COMDATs select the first member. Microsoft vtables select the
    // largest member: partial recovered declarations may emit shorter tables.
    std::map<std::string, std::pair<uint64_t, unsigned>> largest;
    for (unsigned index = 0; index < units.size(); ++index) {
        auto &unit = units[index];
        for (auto &global : unit.raw->globals()) {
            if (!global.hasComdat() || global.getComdat()->getSelectionKind() != Comdat::Largest) continue;
            std::string name = encoded(global.getComdat()->getName());
            uint64_t size = unit.raw->getDataLayout().getTypeAllocSize(global.getValueType());
            auto found = largest.find(name);
            if (found == largest.end() || size > found->second.first) largest[name] = {size, index};
        }
    }
    unsigned discarded = 0;
    for (unsigned index = 0; index < units.size(); ++index) {
        auto &module = *units[index].module;
        SmallVector<GlobalVariable *> losers;
        for (auto &global : module.globals()) {
            if (!global.hasComdat()) continue;
            auto found = largest.find(global.getComdat()->getName().str());
            if (found != largest.end() && found->second.second != index) losers.push_back(&global);
        }
        for (auto *global : losers) {
            std::string name = global->getComdat()->getName().str();
            auto *alias = module.getNamedAlias(name);
            if (!alias) die("largest COMDAT has no public table alias: " + name);
            APInt offset(32, 0);
            if (alias->getAliasee()->stripAndAccumulateConstantOffsets(module.getDataLayout(), offset, true) != global)
                die("unexpected largest COMDAT alias: " + name);
            alias->setName(name + ".discarded");
            auto *external = new GlobalVariable(module, alias->getValueType(), true, GlobalValue::ExternalLinkage, nullptr, name);
            alias->replaceAllUsesWith(external);
            alias->eraseFromParent();
            auto *base = ConstantExpr::getGetElementPtr(Type::getInt8Ty(context), external,
                ConstantInt::get(context, -offset));
            global->replaceAllUsesWith(base);
            global->eraseFromParent();
            ++discarded;
        }
    }
    outs() << "Selected " << largest.size() << " largest COMDAT tables; discarded " << discarded << " partial providers\n";
    std::map<std::string, std::pair<std::string, uint64_t>> fields;
    for (auto &unit : units) {
        for (auto &value : *plan->getObject("fields")) {
            auto locator = value.second.getAsString();
            auto *global = unit.module->getNamedGlobal(*locator);
            if (!global || !global->hasInitializer()) continue;
            APInt offset(32, 0);
            auto *base = global->getInitializer()->stripAndAccumulateConstantOffsets(unit.module->getDataLayout(), offset, true);
            auto *owner = dyn_cast<GlobalVariable>(base);
            if (!owner) die("field locator does not reference data: " + *locator);
            owner->setLinkage(GlobalValue::ExternalLinkage);
            fields[value.first.str()] = {owner->getName().str(), offset.getZExtValue()};
        }
    }
    std::map<std::string, GlobalValue *> definitions;
    std::map<std::string, Prototype> prototypes;
    Module signatures("canonical signatures", context);
    auto stablePrototype = [&](std::string name, Prototype proto) {
        auto *fn = Function::Create(proto.function->getFunctionType(), GlobalValue::ExternalLinkage,
                                    name, signatures);
        fn->setAttributes(proto.function->getAttributes());
        fn->setCallingConv(proto.function->getCallingConv());
        proto.function = fn;
        return proto;
    };
    for (auto &unit : units) {
        for (auto &global : unit.module->global_values()) {
            if (!global.isDeclaration() && !global.hasLocalLinkage()) definitions.emplace(global.getName().str(), &global);
        }
        for (auto &function : *unit.module) {
            if (function.isDeclaration() || function.hasLocalLinkage()) continue;
            Prototype proto = shape(function);
            auto raw = unit.prototypes.find(function.getName().str());
            if (raw != unit.prototypes.end()) { proto.shapes = raw->second.shapes; proto.packed = raw->second.packed; }
            if (!prototypes.count(function.getName().str()))
                prototypes.emplace(function.getName().str(), stablePrototype(function.getName().str(), proto));
        }
    }
    // Placeholder registration declarations (e.g. void FUN_sin()) must not
    // override a real double sin(double) prototype from the same source tree.
    std::map<std::string, unsigned> importScores;
    for (auto &unit : units) for (auto &function : *unit.module) {
        if (!function.isDeclaration() || function.isIntrinsic()) continue;
        auto alias = plan->getObject("aliases")->getString(function.getName());
        std::string name = alias ? alias->str() : function.getName().str();
        if (definitions.count(name)) continue;
        unsigned score = function.arg_size() * 8 + !function.getReturnType()->isVoidTy() * 4;
        if (importScores.count(name) && importScores[name] >= score) continue;
        if (auto *old = signatures.getFunction(name)) { old->setName(name + ".unused"); }
        auto proto = shape(function);
        if (auto raw = unit.prototypes.find(function.getName().str()); raw != unit.prototypes.end()) {
            proto.shapes = raw->second.shapes; proto.packed = raw->second.packed;
        }
        prototypes[name] = stablePrototype(name, proto);
        importScores[name] = score;
    }
    unsigned adjusted = 0;
    std::map<std::string, Prototype> callbacks;
    for (auto &value : *plan->getArray("dispatch")) {
        auto found = prototypes.find(value.getAsString()->str());
        if (found != prototypes.end()) callbacks.emplace(found->first, found->second);
    }
    for (auto &unit : units) {
        auto &module = *unit.module;
        std::map<CallBase *, Prototype> originals;
        for (auto &function : module) for (auto &instruction : instructions(function))
            if (auto *call = dyn_cast<CallBase>(&instruction))
                if (auto *callee = dyn_cast<Function>(call->getCalledOperand()->stripPointerCasts())) {
                    auto raw = unit.prototypes.find(callee->getName().str());
                    originals.emplace(call, raw == unit.prototypes.end() ? shape(*callee) : raw->second);
                }
        SmallVector<GlobalValue *> externals;
        for (auto &global : module.global_values()) if (global.isDeclaration()) externals.push_back(&global);
        for (auto *old : externals) {
            auto alias = plan->getObject("aliases")->getString(old->getName());
            std::string targetName = alias ? alias->str() : old->getName().str();
            auto field = fields.find(targetName);
            if (field != fields.end()) {
                auto [name, offset] = field->second;
                auto *owner = cast<GlobalVariable>(definitions.at(name));
                auto *local = module.getOrInsertGlobal(name, owner->getValueType());
                auto *pointer = ConstantExpr::getGetElementPtr(Type::getInt8Ty(context), local,
                                                ConstantInt::get(Type::getInt32Ty(context), offset));
                old->replaceAllUsesWith(pointer);
                old->eraseFromParent();
                continue;
            }
            auto actual = definitions.find(targetName);
            if (!alias && actual == definitions.end()) continue;
            GlobalValue *target = module.getNamedValue(targetName);
            if (target == old) target = nullptr;
            if (!target && actual != definitions.end()) {
                if (auto *function = dyn_cast<Function>(actual->second)) {
                    if (old->getName() == targetName) old->setName(targetName + ".old");
                    target = declareFunction(module, *function);
                } else if (auto *global = dyn_cast<GlobalVariable>(actual->second)) {
                    if (old->getName() == targetName) old->setName(targetName + ".old");
                    target = cast<GlobalValue>(module.getOrInsertGlobal(targetName, global->getValueType()));
                }
            }
            if (!target) { old->setName(targetName); continue; }
            old->replaceAllUsesWith(target);
            old->eraseFromParent();
        }
        SmallVector<CallBase *> calls;
        for (auto &[call, original] : originals) calls.push_back(call);
        for (auto *call : calls) {
            auto *callee = dyn_cast<Function>(call->getCalledOperand()->stripPointerCasts());
            if (!callee || callee->isIntrinsic()) continue;
            auto actual = prototypes.find(callee->getName().str());
            if (actual == prototypes.end()) continue;
            auto *target = declareFunction(module, *actual->second.function);
            if (target->getFunctionType() != actual->second.function->getFunctionType()) {
                if (!target->isDeclaration()) die("canonical definition type mismatch");
                std::string name = target->getName().str(); target->setName(name + ".old");
                auto *replacement = declareFunction(module, *actual->second.function);
                target->replaceAllUsesWith(replacement); target->eraseFromParent(); target = replacement;
            }
            auto from = originals.at(call);
            if (from.shapes.size() != call->arg_size()) {
                // C's old-style f() declarations allow a call type different
                // from the declaration. Its physical frame is the call's args.
                for (auto param : from.shapes) if (param.frame || param.byval)
                    die("aggregate old-style declaration: " + callee->getName());
                from.shapes.assign(call->arg_size(), Shape{});
                from.packed = false;
            }
            adaptCall(call, from, target, actual->second);
            ++adjusted;
        }
        SmallVector<CallBase *> destroys;
        for(auto &function:module)for(auto &instruction:instructions(function)) {
            auto *call=dyn_cast<CallBase>(&instruction);
            if(!call || isa<Function>(call->getCalledOperand()->stripPointerCasts()) || !call->getType()->isVoidTy() || call->arg_size()!=2)continue;
            if(call->getArgOperand(0)->getType()->isPointerTy() && call->getArgOperand(1)->getType()->isIntegerTy(32))destroys.push_back(call);
        }
        for(auto *call:destroys) {
            IRBuilder<> builder(call);
            auto target=module.getOrInsertFunction("tb_indirect_destroy",builder.getVoidTy(),builder.getPtrTy(),builder.getPtrTy(),builder.getInt32Ty());
            SmallVector<Value*> args={call->getCalledOperand(),call->getArgOperand(0),call->getArgOperand(1)};
            if(auto *invoke=dyn_cast<InvokeInst>(call))builder.CreateInvoke(target,invoke->getNormalDest(),invoke->getUnwindDest(),args);
            else builder.CreateCall(target,args);
            call->eraseFromParent();
        }
        for (auto &function : module) for (auto &instruction : instructions(function)) {
            auto *call = dyn_cast<CallBase>(&instruction);
            if (!call || !call->getCalledFunction() || call->arg_size() != 2 ||
                call->getCalledFunction()->getName() != "scAdd_External_Symbol") continue;
            auto *callback = dyn_cast<Function>(call->getArgOperand(1)->stripPointerCasts());
            if (!callback) continue;
            auto found = prototypes.find(callback->getName().str());
            auto proto = found == prototypes.end() ? shape(*callback) : found->second;
            auto raw = unit.prototypes.find(callback->getName().str());
            if (found == prototypes.end() && raw != unit.prototypes.end()) {
                proto.shapes = raw->second.shapes; proto.packed = raw->second.packed;
            }
            callbacks.emplace(callback->getName().str(), proto);
        }
        if (auto *standard = module.getFunction("scStandardDispatcher")) {
            if (!standard->isDeclaration()) {
                standard->deleteBody();
                IRBuilder<> builder(BasicBlock::Create(context, "entry", standard));
                SmallVector<Value *> args;
                for (auto &arg : standard->args()) args.push_back(&arg);
                builder.CreateCall(module.getOrInsertFunction("tb_seer_dispatch", standard->getFunctionType()), args);
                builder.CreateRetVoid();
            }
        }
        if (verifyModule(module, &errs())) die("verification failed: " + unit.source);
        std::error_code error;
        raw_fd_ostream output(unit.output, error);
        if (error) die(error.message());
        module.print(output, nullptr);
    }
    std::string dispatchPath = std::string(argv[1]);
    dispatchPath = dispatchPath.substr(0, dispatchPath.find_last_of('/') + 1) + "dispatch.ll";
    emitDispatcher(dispatchPath, context, units[0].module->getDataLayoutStr(), callbacks, prototypes);
    outs() << "Rewrote " << units.size() << " modules; examined " << adjusted << " source calls\n";
    return 0;
}
