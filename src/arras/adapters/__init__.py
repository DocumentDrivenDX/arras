# SPDX-License-Identifier: MIT OR Apache-2.0
"""Backend adapters: one subpackage per engine, each implementing the contract in
`arras.backend`. They import only the foundation, domain and contract groups (never `core`, the
doubles or a binding), and the engine's own libraries only inside their own package."""
