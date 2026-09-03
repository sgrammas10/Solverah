"""The out-of-process half of resume text extraction.

Its own directory, and a directory holding nothing else, because
:mod:`solverah.infra.resume_extract.worker` is executed **by path** rather than
imported: ``python <path>/worker.py`` puts that file's directory on
``sys.path[0]``, so a neighbour named after a standard-library module would
shadow it inside the child.  ``solverah/infra/`` already has ``email.py``, and
the standard library's ``email`` is reachable from ``http.client``, which
botocore and pdfminer both sit on top of.  Keeping the worker in a directory of
its own is what stops that from ever being a puzzle to debug.
"""
