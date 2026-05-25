"""Quick COM method signature test - connect to RUNNING Multisim instance."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import win32com.client
import traceback

try:
    print('Connecting to running Multisim...', flush=True)
    app = win32com.client.GetObject(Class='MultisimInterface.MultisimApp')
    print('Connected via GetObject', flush=True)
except Exception:
    print('GetObject failed, trying Dispatch...', flush=True)
    app = win32com.client.Dispatch('MultisimInterface.MultisimApp')
    print('Connected via Dispatch', flush=True)

# The MCP server already opened the file, get the active circuit
# Try different ways to get the circuit
print('\nTrying to get circuit...', flush=True)
circ = None
for method in ['ActiveCircuit', 'Circuit']:
    try:
        circ = getattr(app, method)
        print(f'app.{method} => {circ}', flush=True)
        break
    except Exception as e:
        print(f'app.{method} => {e}', flush=True)

if circ is None:
    # Maybe the app.OpenFile returns it?  skip re-open
    print('Cannot get circuit object. Trying OpenFile...', flush=True)
    circ = app.OpenFile(r'C:\Users\ES&E\Documents\模电实验\2-1.ms14')
    print(f'OpenFile => {circ}', flush=True)

if circ is None:
    print('No circuit object available. Exiting.', flush=True)
    sys.exit(1)

print(f'\nCircuit object: {circ}', flush=True)

# Enumerate what methods/props are available via IDispatch
print('\n--- Testing Methods ---', flush=True)

# Test ReportBOM with different arg counts
print('\n[ReportBOM]', flush=True)
for args in [(), (0,), (1,), ('',), (0, 0), (1, 0)]:
    try:
        r = circ.ReportBOM(*args)
        print(f'  ReportBOM{args} => OK, len={len(str(r))}', flush=True)
        print(f'  Content: {repr(str(r))[:200]}', flush=True)
        break
    except Exception as e:
        print(f'  ReportBOM{args} => {e}', flush=True)

# Test ReportNetList
print('\n[ReportNetList]', flush=True)
for args in [(), (0,), (1,), (2,), ('SPICE',), (0, 0), (0, ''), ('', 0)]:
    try:
        r = circ.ReportNetList(*args)
        print(f'  ReportNetList{args} => OK, len={len(str(r))}', flush=True)
        print(f'  Content: {repr(str(r))[:200]}', flush=True)
        break
    except Exception as e:
        print(f'  ReportNetList{args} => {e}', flush=True)

# Test GetCircuitImage
print('\n[GetCircuitImage]', flush=True)
test_path = r'C:\Users\ES&E\Documents\模电实验\test_img.png'
for label, args in [
    ('(fmt,)', (0,)),
    ('(fmt=1)', (1,)),
    ('(fmt=2)', (2,)),
    ('(path, fmt)', (test_path, 0)),
    ('(fmt, path)', (0, test_path)),
    ('(path,)', (test_path,)),
    ('()', ()),
]:
    try:
        r = circ.GetCircuitImage(*args)
        print(f'  GetCircuitImage {label} => OK, type={type(r).__name__}, val={repr(r)[:200]}', flush=True)
        break
    except Exception as e:
        print(f'  GetCircuitImage {label} => {e}', flush=True)

# Test EnumOutputs
print('\n[EnumOutputs]', flush=True)
for args in [(), (0,), (1,), (2,), (3,)]:
    try:
        r = circ.EnumOutputs(*args)
        result = list(r) if r else []
        print(f'  EnumOutputs{args} => {result}', flush=True)
    except Exception as e:
        print(f'  EnumOutputs{args} => {e}', flush=True)

print('\nDone.', flush=True)

# Test ReportBOM
print('\n--- ReportBOM ---')
for args in [(), (0,), (1,), (0, 0)]:
    try:
        r = circ.ReportBOM(*args)
        print(f'ReportBOM{args} => OK, len={len(str(r))}')
        print(repr(str(r))[:300])
        break
    except Exception as e:
        print(f'ReportBOM{args} => {e}')

# Test ReportNetList
print('\n--- ReportNetList ---')
for args in [(), (0,), (1,), (2,), (0, 0)]:
    try:
        r = circ.ReportNetList(*args)
        print(f'ReportNetList{args} => OK, len={len(str(r))}')
        print(repr(str(r))[:300])
        break
    except Exception as e:
        print(f'ReportNetList{args} => {e}')

# Test GetCircuitImage
print('\n--- GetCircuitImage ---')
test_path = r'C:\Users\ES&E\Documents\模电实验\test_img.png'
# Try (path, format), (format, path), (format,), (path,)
for label, args in [
    ('(path, 0)', (test_path, 0)),
    ('(0, path)', (0, test_path)),
    ('(path,)', (test_path,)),
    ('(0,)', (0,)),
    ('()', ()),
]:
    try:
        r = circ.GetCircuitImage(*args)
        print(f'GetCircuitImage {label} => OK, result={repr(r)[:200]}')
        break
    except Exception as e:
        print(f'GetCircuitImage {label} => {e}')

# List available probes/outputs
print('\n--- EnumOutputs ---')
for args in [(), (0,), (1,), (2,)]:
    try:
        r = circ.EnumOutputs(*args)
        print(f'EnumOutputs{args} => {list(r) if r else "empty"}')
        break
    except Exception as e:
        print(f'EnumOutputs{args} => {e}')

app.Quit()
