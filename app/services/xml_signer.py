from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree
from signxml import XMLSigner

from app.services.crypto import decrypt_bytes, decrypt_string

_DS_NS = "http://www.w3.org/2000/09/xmldsig#"
_EXT_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"


def sign_xml(xml_str: str, encrypted_pfx: bytes, encrypted_password: str) -> str:
    """Sign XML with the client's PFX certificate.

    The signature is placed inside ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent
    as required by SUNAT for UBL 2.1 electronic documents.
    """
    pfx_data = decrypt_bytes(encrypted_pfx)
    pfx_password = decrypt_string(encrypted_password).encode()

    private_key, certificate, chain = pkcs12.load_key_and_certificates(
        pfx_data, pfx_password
    )

    root = etree.fromstring(xml_str.encode())

    signer = XMLSigner(
        signature_algorithm="rsa-sha256",
        digest_algorithm="sha256",
        c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
    )

    signed_root = signer.sign(
        root,
        key=private_key,
        cert=[certificate] + (list(chain) if chain else []),
        always_add_key_value=False,
    )

    # Move ds:Signature into ExtensionContent (SUNAT requirement)
    # Must search on signed_root since sign() may return a new tree
    ext_content = signed_root.find(
        f".//{{{_EXT_NS}}}UBLExtensions/{{{_EXT_NS}}}UBLExtension/{{{_EXT_NS}}}ExtensionContent"
    )
    if ext_content is not None:
        signature = signed_root.find(f"{{{_DS_NS}}}Signature")
        if signature is not None:
            signed_root.remove(signature)
            ext_content.append(signature)

    return etree.tostring(signed_root, xml_declaration=True, encoding="UTF-8").decode()
