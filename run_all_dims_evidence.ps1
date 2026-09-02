$venvPython = (Resolve-Path "..\.venv-solverah-3b\Scripts\python.exe").Path

Copy-Item causal_graph\scorer_pipeline.py ..\decision_test\causal_graph\ -Force
Copy-Item causal_graph\run_all_dims_evidence.py ..\decision_test\causal_graph\ -Force

Set-Location ..\decision_test\causal_graph
$env:SOLVERAH_IP_DIR = "../ip_test"
& $venvPython run_all_dims_evidence.py
