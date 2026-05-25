"""Extract method signatures from Multisim COM type library."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import pythoncom
import win32com.client

# Get the TypeLib for MultisimInterface
# CLSID: {D9CBB7A1-6AD6-438B-AD1B-42FB2DB00CAE}
# TypeLib GUID from registry: {D360240D-8F60-4FBC-AEC2-B6E14C3042B8}

try:
    # Load type library
    tlb = pythoncom.LoadRegTypeLib(
        '{D360240D-8F60-4FBC-AEC2-B6E14C3042B8}', 1, 0, 0
    )
    print(f'TypeLib loaded, {tlb.GetTypeInfoCount()} type infos', flush=True)

    for i in range(tlb.GetTypeInfoCount()):
        name = tlb.GetDocumentation(i)[0]
        ti = tlb.GetTypeInfo(i)
        ta = ti.GetTypeAttr()
        kind_names = {0: 'ENUM', 1: 'RECORD', 2: 'MODULE', 3: 'INTERFACE',
                      4: 'DISPATCH', 5: 'COCLASS', 6: 'ALIAS'}
        kind = kind_names.get(ta.typekind, str(ta.typekind))

        if kind in ('DISPATCH', 'INTERFACE') and name in (
            'IMultisimApp', 'IMultisimCircuit',
            'MultisimApp', 'MultisimCircuit',
            '_IMultisimApp', '_IMultisimCircuit',
        ):
            print(f'\n=== {name} ({kind}) ===', flush=True)
            print(f'  Methods/Props: {ta.cFuncs}', flush=True)

            for j in range(ta.cFuncs):
                fd = ti.GetFuncDesc(j)
                names = ti.GetNames(fd.memid)
                func_name = names[0] if names else '?'
                param_names = names[1:] if len(names) > 1 else []

                invoke_kinds = {1: 'METHOD', 2: 'PROPGET', 4: 'PROPPUT', 8: 'PROPPUTREF'}
                invoke_kind = invoke_kinds.get(fd.invkind, str(fd.invkind))

                vt_names = {
                    0: 'VT_EMPTY', 2: 'VT_I2', 3: 'VT_I4', 4: 'VT_R4',
                    5: 'VT_R8', 6: 'VT_CY', 7: 'VT_DATE', 8: 'VT_BSTR',
                    9: 'VT_DISPATCH', 10: 'VT_ERROR', 11: 'VT_BOOL',
                    12: 'VT_VARIANT', 13: 'VT_UNKNOWN', 24: 'VT_VOID',
                    25: 'VT_HRESULT', 0x2000: 'VT_ARRAY', 0x4000: 'VT_BYREF',
                }

                def vt_str(vt):
                    base = vt & 0xFFF
                    flags = []
                    if vt & 0x2000:
                        flags.append('ARRAY')
                    if vt & 0x4000:
                        flags.append('BYREF')
                    name_s = vt_names.get(base, f'0x{base:x}')
                    if flags:
                        return f'{"|".join(flags)}({name_s})'
                    return name_s

                ret_type = vt_str(fd.rettype[0]) if fd.rettype else '?'

                params_str = []
                for k, (tdesc, pflags) in enumerate(fd.args):
                    pname = param_names[k] if k < len(param_names) else f'p{k}'
                    ptype = vt_str(tdesc)
                    flag_strs = []
                    if pflags & 1: flag_strs.append('IN')
                    if pflags & 2: flag_strs.append('OUT')
                    if pflags & 16: flag_strs.append('RETVAL')
                    flag_str = f'[{",".join(flag_strs)}]' if flag_strs else ''
                    params_str.append(f'{pname}: {ptype} {flag_str}')

                params_display = ', '.join(params_str) if params_str else ''

                # Only print methods we care about
                interesting = [
                    'ReportBOM', 'ReportNetList', 'GetCircuitImage',
                    'EnumOutputs', 'EnumComponents', 'EnumSections',
                    'RLCValue', 'CircuitParameterValue',
                    'GetOutputData', 'DoTransient', 'DoACSweep',
                    'DoACSingleFrequency', 'DoDCOperatingPoint',
                    'SetOutputRequest', 'ClearOutputRequest',
                    'Run', 'Stop', 'Pause', 'Resume',
                    'RunUntilNextOutput', 'IsOutputReady',
                    'CreateSnippet', 'SaveDesignAsSnippet',
                    'Visible', 'AppVersion',
                ]
                if func_name in interesting or not interesting:
                    print(f'  {invoke_kind:10} {func_name}({params_display}) -> {ret_type}', flush=True)

except Exception as e:
    print(f'ERROR: {e}', flush=True)
    import traceback
    traceback.print_exc()
