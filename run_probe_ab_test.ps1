# A/B the two probe designs on the SAME pre-registered boundary test set.
# 12 API calls total (6 dimensions x 2 probe designs).
$venvPython = (Resolve-Path "..\.venv-solverah-3b\Scripts\python.exe").Path

Copy-Item causal_graph\scorer_pipeline.py ..\decision_test\causal_graph\ -Force
Copy-Item causal_graph\extremity_flag.py ..\decision_test\causal_graph\ -Force
Copy-Item causal_graph\probe_boundary_test.py ..\decision_test\causal_graph\ -Force

Set-Location ..\decision_test\causal_graph
$env:SOLVERAH_IP_DIR = "../ip_test"

Write-Host ""
Write-Host "######## FORCED-CHOICE PROBE (the proposed fix) ########"
Write-Host ""
& $venvPython probe_boundary_test.py --probe forced
