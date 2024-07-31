Notes (for developers)
======================

Place here documents that can be useful for developers, such as:

- TODO lists
- Architecture Decision Records (ADRs)

(This may, or may not, be the best place for these documents. We can move them later if needed, for instance into the documentation.)


## Additional notes

### Framework for CLI

We're currently using [rpyc](https://rpyc.readthedocs.io/en/latest/) as the RPC mechanism between the CLI and and the server.

We may switch to something else in the future, and this should be considered an implementation detail.
