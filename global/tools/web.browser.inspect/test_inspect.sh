#!/bin/bash
# Test Suite for web.browser.inspect Atom
# 3 Trials Minimum Before [REQUIRES_PROMOTER_REVIEW]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ATOM_DIR="$SCRIPT_DIR"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
RESULTS_FILE="$ATOM_DIR/trials.json"
TMP_DIR="$ATOM_DIR/.test_tmp"
mkdir -p "$TMP_DIR"

echo '[]' > "$RESULTS_FILE"

add_trial() {
    local trial_id="$1"
    local result="$2"
    local target="$3"
    local output_file="$4"
    local gates_passed="$5"
    local gates_failed="$6"
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    python3 -c "
import json, sys
with open(sys.argv[5], 'r') as f:
    output = f.read()
entry = {
    'trial_id': sys.argv[1],
    'ts': sys.argv[2],
    'result': int(sys.argv[3]),
    'target': sys.argv[4],
    'output': output[:200],
    'gates_passed': [g for g in sys.argv[6].split(',') if g],
    'gates_failed': [g for g in sys.argv[7].split(',') if g]
}
with open('$RESULTS_FILE', 'r') as f:
    trials = json.load(f)
trials.append(entry)
with open('$RESULTS_FILE', 'w') as f:
    json.dump(trials, f, indent=2)
" "$trial_id" "$ts" "$result" "$target" "$output_file" "$gates_passed" "$gates_failed"
    
    echo "  Trial $trial_id: $(if [ $result -eq 1 ]; then echo PASS; else echo FAIL; fi) - $target"
}

echo "=========================================="
echo "web.browser.inspect Atom Test Suite"
echo "=========================================="
echo ""

# Trial 1: Basic page inspection
echo "Trial 1: Basic page inspection on example.com"
echo "----------------------------------------------"

$VENV_PYTHON "$ATOM_DIR/browser_inspect.py" --url "https://example.com" --max-chars 500 --include-interactive > "$TMP_DIR/t1_output.json" 2>&1 || true

# Gate validation
python3 -c "
import json, sys
with open('$TMP_DIR/t1_output.json', 'r') as f:
    data = json.load(f)

passed = []
failed = []

# Gate: summary_under_limit
if len(data.get('summary', '')) <= 500:
    passed.append('summary_under_limit')
else:
    failed.append('summary_under_limit')

# Gate: page_id_present
if data.get('page_id') and len(data['page_id']) > 0:
    passed.append('page_id_present')
else:
    failed.append('page_id_present')

# Gate: interactive_elements_valid
elements = data.get('interactive_elements', [])
if all(e.get('ref_id') and e.get('tag') and e.get('type') for e in elements):
    passed.append('interactive_elements_valid')
else:
    failed.append('interactive_elements_valid')

# Gate: valid_json (already parsed, so it passed)
passed.append('valid_json')

result = 1 if len(failed) == 0 else 0
print(result)
print(','.join(passed))
print(','.join(failed))
" > "$TMP_DIR/t1_gates.txt" 2>&1

T1_RESULT=$(sed -n '1p' "$TMP_DIR/t1_gates.txt")
T1_PASSED=$(sed -n '2p' "$TMP_DIR/t1_gates.txt")
T1_FAILED=$(sed -n '3p' "$TMP_DIR/t1_gates.txt")
add_trial "T1-basic" "$T1_RESULT" "Basic page inspection on example.com" "$TMP_DIR/t1_output.json" "$T1_PASSED" "$T1_FAILED"

echo ""

# Trial 2: Drill
echo "Trial 2: Drill into element from Trial 1"
echo "----------------------------------------------"

# Get page_id and ref_id from trial 1
python3 -c "
import json
with open('$TMP_DIR/t1_output.json', 'r') as f:
    data = json.load(f)
page_id = data.get('page_id', '')
elements = data.get('interactive_elements', [])
ref_id = elements[0]['ref_id'] if elements else 'none'
print(page_id)
print(ref_id)
" > "$TMP_DIR/t2_vars.txt"

T2_PAGE_ID=$(sed -n '1p' "$TMP_DIR/t2_vars.txt")
T2_REF_ID=$(sed -n '2p' "$TMP_DIR/t2_vars.txt")

if [ "$T2_REF_ID" != "none" ] && [ -n "$T2_PAGE_ID" ]; then
    $VENV_PYTHON "$ATOM_DIR/browser_drill.py" --page-id "$T2_PAGE_ID" --ref-id "$T2_REF_ID" --url "https://example.com" > "$TMP_DIR/t2_output.json" 2>&1 || true
    
    python3 -c "
import json, sys
with open('$TMP_DIR/t2_output.json', 'r') as f:
    data = json.load(f)

passed = []
failed = []

# Gate: element_exists
detail = data.get('detail', {})
if isinstance(detail, dict) and 'tag' in detail:
    passed.append('element_exists')
else:
    failed.append('element_exists')

# Gate: detail_non_empty
if isinstance(detail, (dict, str)) and len(str(detail)) > 10:
    passed.append('detail_non_empty')
else:
    failed.append('detail_non_empty')

passed.append('valid_json')

result = 1 if len(failed) == 0 else 0
print(result)
print(','.join(passed))
print(','.join(failed))
" > "$TMP_DIR/t2_gates.txt" 2>&1
    
    T2_RESULT=$(sed -n '1p' "$TMP_DIR/t2_gates.txt")
    T2_PASSED=$(sed -n '2p' "$TMP_DIR/t2_gates.txt")
    T2_FAILED=$(sed -n '3p' "$TMP_DIR/t2_gates.txt")
    add_trial "T2-drill" "$T2_RESULT" "Drill into element $T2_REF_ID from example.com" "$TMP_DIR/t2_output.json" "$T2_PASSED" "$T2_FAILED"
else
    add_trial "T2-drill" "0" "Drill into element (no elements)" "" "" "no_elements"
fi

echo ""

# Trial 3: Screenshot
echo "Trial 3: Screenshot action on example.com"
echo "----------------------------------------------"

$VENV_PYTHON "$ATOM_DIR/browser_interact.py" --page-id "test_page_1" --action "screenshot" --ref-id "@e1" --url "https://example.com" > "$TMP_DIR/t3_output.json" 2>&1 || true

python3 -c "
import json, os, sys
with open('$TMP_DIR/t3_output.json', 'r') as f:
    data = json.load(f)

passed = []
failed = []

# Gate: action_valid
if data.get('action') in ['click', 'type', 'hover', 'scroll', 'screenshot']:
    passed.append('action_valid')
else:
    failed.append('action_valid')

# Gate: status_indicated
if data.get('status') in ['success', 'failure', 'error']:
    passed.append('status_indicated')
else:
    failed.append('status_indicated')

# Gate: screenshot_saved
screenshot_path = data.get('screenshot_path', '')
if screenshot_path and os.path.exists(screenshot_path):
    passed.append('screenshot_saved')
else:
    failed.append('screenshot_saved')

passed.append('valid_json')

result = 1 if len(failed) == 0 else 0
print(result)
print(','.join(passed))
print(','.join(failed))
" > "$TMP_DIR/t3_gates.txt" 2>&1

T3_RESULT=$(sed -n '1p' "$TMP_DIR/t3_gates.txt")
T3_PASSED=$(sed -n '2p' "$TMP_DIR/t3_gates.txt")
T3_FAILED=$(sed -n '3p' "$TMP_DIR/t3_gates.txt")
add_trial "T3-screenshot" "$T3_RESULT" "Screenshot action on example.com" "$TMP_DIR/t3_output.json" "$T3_PASSED" "$T3_FAILED"

echo ""
echo "=========================================="
echo "Test Suite Complete"
echo "=========================================="
echo ""

$VENV_PYTHON -c "
import json
with open('$RESULTS_FILE', 'r') as f:
    trials = json.load(f)

passed = sum(1 for t in trials if t['result'] == 1)
failed = sum(1 for t in trials if t['result'] == 0)
total = len(trials)

print('Results: {}/{} passed, {}/{} failed'.format(passed, total, failed, total))
print()
for t in trials:
    status = 'PASS' if t['result'] == 1 else 'FAIL'
    print('{} | {} | {}'.format(status, t['trial_id'], t['target']))

print()
if failed == 0 and total >= 3:
    print('[ALL_TRIALS_PASSED]')
    print('[REQUIRES_PROMOTER_REVIEW]')
else:
    print('[TRIALS_INCOMPLETE]')
    print('Need 3 passed trials before [REQUIRES_PROMOTER_REVIEW]')
"

# Cleanup
echo ""
echo "Cleanup: Removing test artifacts..."
rm -rf "$TMP_DIR"
rm -f /tmp/screenshot_*.png

echo ""
echo "Full results saved to: $RESULTS_FILE"
