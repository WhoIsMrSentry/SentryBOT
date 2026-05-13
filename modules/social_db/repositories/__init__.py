"""Repository classes for the unified social store.

Each repository wraps a thread-safe :class:`SocialDB` connection and provides a
focused CRUD/query surface for a single table. Repositories do not maintain
state of their own besides the back-reference to the parent store.
"""
