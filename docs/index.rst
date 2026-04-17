Code Documentation
==================

This is the Sphinx-generated code documentation for the P2P file-sharing
project.

Overview
--------

The program lets peers share files without using a central server. Each peer
can discover other peers, search for files, download files in chunks, verify
hashes, send chat messages, and filter search results by file type.

Command Line Example
--------------------

Start two peers in separate terminals:

.. code-block:: powershell

   python -m p2p_share.cli --shared-dir shared_a --download-dir downloads_a --port 9001
   python -m p2p_share.cli --shared-dir shared_b --download-dir downloads_b --port 9002

Example commands:

.. code-block:: text

   connect 127.0.0.1 9001
   search notes
   type txt
   message 127.0.0.1 9001 hello
   messages
   download 127.0.0.1 9001 <file_id>

Contents
--------

.. toctree::
   :maxdepth: 2

   modules
```

Create `docs/modules.rst`:

```rst
Code Modules
============

p2p_share.cli
-------------

.. automodule:: p2p_share.cli
   :members:

p2p_share.config
----------------

.. automodule:: p2p_share.config
   :members:

p2p_share.index
---------------

.. automodule:: p2p_share.index
   :members:

p2p_share.peer
--------------

.. automodule:: p2p_share.peer
   :members:

p2p_share.protocol
------------------

.. automodule:: p2p_share.protocol
   :members: