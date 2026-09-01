# Third probe design: forced choice among all 5 bands PLUS an explicit
# "this fragment isn't about this property" opt-out. 6 API calls.
$venvPython = (Resolve-Path "..\.venv-solverah-3b\Scripts\python.exe").Path

Copy-Item causal_graph\scorer_pipeline.py ..\decision_test\causal_graph\ -Force
Copy-Item causal_graph\extremity_flag.py ..\decision_test\causal_graph\ -Force
Copy-Item causal_graph\probe_boundary_test.py ..\decision_test\causal_graph\ -Force

Set-Location ..\decision_test\causal_graph
$env:SOLVERAH_IP_DIR = "../ip_test"
& $venvPython probe_boundary_test.py --probe forced_escape
