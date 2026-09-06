# Run from the Solverah repo root (Desktop\Solverah).
# Resolve the venv's python.exe explicitly -- on Windows a venv only ships
# python.exe (no python3.exe), so a bare `python3` call skips the venv
# entirely and silently falls through to the Microsoft Store alias /
# whatever Python is on system PATH. Always invoke by path instead.
$venvPython = (Resolve-Path "..\.venv-solverah-3b\Scripts\python.exe").Path

New-Item -ItemType Directory -Force -Path ..\decision_test\causal_graph | Out-Null
New-Item -ItemType Directory -Force -Path ..\decision_test\ip_test\ground_truth\rater_app | Out-Null
New-Item -ItemType Directory -Force -Path ..\decision_test\ip_test\ground_truth\anonymization | Out-Null

Copy-Item causal_graph\scorer_variance_test_v2.py ..\decision_test\causal_graph\ -Force
Copy-Item causal_graph\_test_anchors_v1_with_v3decision.json ..\decision_test\ip_test\ground_truth\rater_app\anchors.json -Force
Copy-Item Solverah_IP\ground_truth\anonymization\P-0*_packet_ANON.txt ..\decision_test\ip_test\ground_truth\anonymization\ -Force
Copy-Item .env ..\decision_test\.env -Force

Set-Location ..\decision_test\causal_graph
& $venvPython -m pip install --quiet openai python-dotenv pandas

$env:SOLVERAH_IP_DIR = "../ip_test"
foreach ($pk in @("P-01","P-02","P-03","P-04","P-05","P-06")) {
    Write-Host "=== $pk ==="
    & $venvPython scorer_variance_test_v2.py --packet $pk
}
