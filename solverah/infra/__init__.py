"""Adapters for everything outside the process: object storage, email, LLMs.

See docs/ARCHITECTURE.md 2.2.  Nothing here holds business rules -- an adapter
knows how to talk to one system and nothing about why it is being asked to.
Services depend on these; these depend on nothing in the application.

The modules are also the seam tests substitute at.  They were previously
function-local imports and module-level globals inside ``app.py``
(``get_s3_client``, ``_get_openai_client``, ``send_confirmation_email``), which
meant the only way to stub a provider was to patch a name on a 4,000-line
module that had to be imported -- and booted -- first.
"""
