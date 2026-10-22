// Lower MS x86 varargs to an explicit packed argument buffer before retargeting.
// Every translated module uses this private ABI, including calls through pointers.
// Native Wasm libc must supply explicit adapters for titbit_va_* imports.
#include <llvm/IR/Constants.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/InstIterator.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/Support/SourceMgr.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/Support/MathExtras.h>
#include <algorithm>
#include <cstdlib>

using namespace llvm;

static FunctionType *packedType(FunctionType *type) {
    SmallVector<Type *> params(type->params());
    params.push_back(PointerType::getUnqual(type->getContext()));
    return FunctionType::get(type->getReturnType(), params, false);
}

static AttributeList packedAttributes(LLVMContext &context, AttributeList attrs,
                                      unsigned fixed) {
    SmallVector<AttributeSet> params;
    for (unsigned i = 0; i < fixed; ++i) params.push_back(attrs.getParamAttrs(i));
    params.push_back(AttributeSet());
    // va_start used to access an implicit area; it now reads an explicit pointer.
    auto fn = attrs.getFnAttrs().removeAttribute(context, Attribute::Memory);
    return AttributeList::get(context, fn, attrs.getRetAttrs(), params);
}

static void fail(const Twine &message) {
    errs() << "MS x86 packed varargs: " << message << '\n';
    exit(1);
}

static void lower(Module &module) {
    auto &context = module.getContext();
    const auto &layout = module.getDataLayout();
    if (!StringRef(module.getTargetTriple()).starts_with("i386-pc-windows-msvc") ||
        layout.getPointerSize() != 4)
        fail("expected Microsoft i386 source IR");

    SmallVector<CallBase *> calls;
    SmallVector<Function *> functions;
    SmallVector<IntrinsicInst *> intrinsics;
    for (auto &fn : module) {
        if (fn.isVarArg() && !fn.isIntrinsic()) functions.push_back(&fn);
        for (auto &inst : instructions(fn)) {
            if (isa<VAArgInst>(inst)) fail("va_arg instruction requires source slot macros");
            if (auto *intrinsic = dyn_cast<IntrinsicInst>(&inst)) {
                auto id = intrinsic->getIntrinsicID();
                if (id == Intrinsic::vastart || id == Intrinsic::vaend ||
                    id == Intrinsic::vacopy) intrinsics.push_back(intrinsic);
            }
            if (auto *call = dyn_cast<CallBase>(&inst)) {
                if (call->getFunctionType()->isVarArg() &&
                    !(call->getCalledFunction() && call->getCalledFunction()->isIntrinsic()))
                    calls.push_back(call);
            }
        }
    }

    // Change declarations and definitions together. Opaque pointers let globals,
    // aliases, callback tables and recursive uses retain the same function address.
    for (auto *old : functions) {
        if (module.getNamedValue(("titbit_va_" + old->getName()).str()))
            fail("reserved packed-varargs symbol collision");
        auto *fn = Function::Create(packedType(old->getFunctionType()), old->getLinkage(),
                                    old->getAddressSpace(), "", &module);
        fn->copyAttributesFrom(old);
        fn->setAttributes(packedAttributes(context, old->getAttributes(), old->arg_size()));
        fn->takeName(old);
        fn->setName("titbit_va_" + fn->getName());
        fn->splice(fn->end(), old);
        auto replacement = fn->arg_begin();
        for (auto &arg : old->args()) {
            replacement->takeName(&arg);
            arg.replaceAllUsesWith(&*replacement++);
        }
        replacement->setName("titbit.varargs");
        old->replaceAllUsesWith(fn);
        old->eraseFromParent();
    }

    for (auto *inst : intrinsics) {
        IRBuilder<> builder(inst);
        switch (inst->getIntrinsicID()) {
        case Intrinsic::vastart:
            if (!inst->getFunction()->getName().starts_with("titbit_va_"))
                fail("va_start outside translated variadic function");
            builder.CreateAlignedStore(inst->getFunction()->getArg(
                inst->getFunction()->arg_size() - 1), inst->getArgOperand(0), Align(4));
            break;
        case Intrinsic::vacopy:
            builder.CreateAlignedStore(builder.CreateAlignedLoad(
                builder.getPtrTy(), inst->getArgOperand(1), Align(4)),
                inst->getArgOperand(0), Align(4));
            break;
        default: break; // va_end has no work for a packed pointer.
        }
        inst->eraseFromParent();
    }

    for (auto *call : calls) {
        auto *type = call->getFunctionType();
        unsigned fixed = type->getNumParams();
        if (!isa<CallInst>(call) && !isa<InvokeInst>(call)) fail("unsupported callbr");
        if (auto *ci = dyn_cast<CallInst>(call))
            if (ci->isMustTailCall()) fail("musttail cannot pass a caller-owned buffer");
        uint64_t bytes = 0;
        SmallVector<uint64_t> offsets;
        for (unsigned i = fixed; i < call->arg_size(); ++i) {
            if (call->paramHasAttr(i, Attribute::InAlloca) ||
                call->paramHasAttr(i, Attribute::Preallocated))
                fail("variadic inalloca/preallocated argument needs a source adapter");
            auto *argType = call->paramHasAttr(i, Attribute::ByVal)
                ? call->getParamByValType(i) : call->getArgOperand(i)->getType();
            if (!argType->isSized() || argType->isVectorTy()) fail("unsupported slot type");
            offsets.push_back(bytes);
            bytes += alignTo(layout.getTypeAllocSize(argType).getFixedValue(), 4);
        }
        // One fixed-size allocation per call site in the entry block. A call
        // inside a loop must not consume more linear stack space each iteration.
        IRBuilder<> entry(&*call->getFunction()->getEntryBlock().getFirstInsertionPt());
        auto *buffer = entry.CreateAlloca(ArrayType::get(entry.getInt8Ty(), std::max(bytes, uint64_t(4))),
                                          nullptr, "titbit.slots");
        buffer->setAlignment(Align(4));
        IRBuilder<> builder(call);
        for (unsigned i = fixed; i < call->arg_size(); ++i) {
            auto *slot = builder.CreateConstGEP1_32(builder.getInt8Ty(), buffer, offsets[i - fixed]);
            if (call->paramHasAttr(i, Attribute::ByVal)) {
                auto size = layout.getTypeAllocSize(call->getParamByValType(i)).getFixedValue();
                builder.CreateMemCpy(slot, Align(4), call->getArgOperand(i),
                                     call->getParamAlign(i).valueOrOne(), size);
            } else {
                builder.CreateAlignedStore(call->getArgOperand(i), slot, Align(4));
            }
        }
        SmallVector<Value *> args;
        for (unsigned i = 0; i < fixed; ++i) args.push_back(call->getArgOperand(i));
        args.push_back(buffer);
        SmallVector<OperandBundleDef> bundles;
        call->getOperandBundlesAsDefs(bundles);
        CallBase *replacement;
        if (auto *invoke = dyn_cast<InvokeInst>(call)) {
            replacement = builder.CreateInvoke(packedType(type), call->getCalledOperand(),
                invoke->getNormalDest(), invoke->getUnwindDest(), args, bundles);
        } else {
            // Tail calls cannot discard the frame containing the packed buffer.
            replacement = builder.CreateCall(packedType(type), call->getCalledOperand(), args, bundles);
        }
        replacement->setCallingConv(call->getCallingConv());
        replacement->setAttributes(packedAttributes(context, call->getAttributes(), fixed));
        replacement->copyMetadata(*call);
        replacement->setDebugLoc(call->getDebugLoc());
        replacement->takeName(call);
        call->replaceAllUsesWith(replacement);
        call->eraseFromParent();
    }
}

int main(int argc, char **argv) {
    if (argc != 3) { errs() << "Usage: wasm-varargs input.ms.ll output.ms.ll\n"; return 1; }
    LLVMContext context;
    SMDiagnostic diagnostic;
    auto module = parseIRFile(argv[1], diagnostic, context);
    if (!module) { diagnostic.print(argv[0], errs()); return 1; }
    lower(*module);
    if (verifyModule(*module, &errs())) return 1;
    std::error_code error;
    raw_fd_ostream output(argv[2], error);
    if (error) { errs() << error.message() << '\n'; return 1; }
    module->print(output, nullptr);
    return 0;
}
