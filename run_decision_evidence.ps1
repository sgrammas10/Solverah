# Run from the Solverah repo root (Desktop\Solverah), fresh terminal is fine --
# nothing here depends on state from the earlier run_decision_test.ps1 session.
$venvPython = (Resolve-Path "..\.venv-solverah-3b\Scripts\python.exe").Path

Copy-Item causal_graph\scorer_pipeline.py ..\decision_test\causal_graph\ -Force
Copy-Item causal_graph\run_decision_evidence.py ..\decision_test\causal_graph\ -Force

Set-Location ..\decision_test\causal_graph
$env:SOLVERAH_IP_DIR = "../ip_test"
& $venvPython run_decision_evidence.py
