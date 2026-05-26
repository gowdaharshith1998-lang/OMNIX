"""ML-DSA-65 signed receipt machinery for OMNIX-DM manifests.

Public surface (sign-then-emit-both atomic):
    schemas.COLUMN_MAPPING_MANIFEST_SCHEMA
    schemas.EDGE_CASE_MANIFEST_SCHEMA
    ml_dsa_65_signer.sign_canonical(payload) -> (canonical_json, signature_hex)
    merkle_chain.next_hash(predecessor_hash, canonical_json) -> str
"""
