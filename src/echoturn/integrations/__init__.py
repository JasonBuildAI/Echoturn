"""Adapters from the pipeline to whatever the host serves it with.

These live behind extras so the core stays free of web frameworks: the pipeline
produces events, and shipping them over HTTP is one way to consume them, not a
requirement of the package.
"""
