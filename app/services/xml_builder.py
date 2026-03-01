from decimal import Decimal

from lxml import etree

NAMESPACES = {
    None: "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ccts": "urn:un:unece:uncefact:documentation:2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "qdt": "urn:oasis:names:specification:ubl:schema:xsd:QualifiedDatatypes-2",
    "udt": "urn:un:unece:uncefact:data:specification:UnqualifiedDataTypesSchemaModule:2",
}

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"

# Catálogo 05 - Tax scheme mapping by igv_type prefix
TAX_SCHEMES = {
    "1": {"id": "1000", "name": "IGV", "code": "VAT"},       # Gravado
    "2": {"id": "9997", "name": "EXO", "code": "VAT"},       # Exonerado
    "3": {"id": "9998", "name": "INA", "code": "FRE"},       # Inafecto
}


def _el(parent, ns, tag, text=None, **attribs):
    el = etree.SubElement(parent, f"{{{ns}}}{tag}" if ns else tag, **attribs)
    if text is not None:
        el.text = str(text)
    return el


def _amount(parent, ns, tag, value, currency="PEN"):
    """Format monetary amounts with exactly 2 decimal places."""
    _el(parent, ns, tag, f"{Decimal(value):.2f}", currencyID=currency)


def _price(parent, ns, tag, value, currency="PEN"):
    """Format unit prices with up to 10 decimal places (strips trailing zeros)."""
    formatted = f"{Decimal(value):.10f}".rstrip("0")
    if formatted.endswith("."):
        formatted += "0"
    _el(parent, ns, tag, formatted, currencyID=currency)


def _quantity(parent, ns, tag, value, unit_code="NIU"):
    """Format quantities with up to 10 decimal places."""
    formatted = f"{Decimal(value):.10f}".rstrip("0")
    if formatted.endswith("."):
        formatted += "0"
    _el(
        parent, ns, tag, formatted,
        unitCode=unit_code,
        unitCodeListID="UN/ECE rec 20",
        unitCodeListAgencyName="United Nations Economic Commission for Europe",
    )


def build_invoice_xml(
    *,
    document_type: str,
    series: str,
    correlative: int,
    issue_date: str,
    currency: str,
    supplier_ruc: str,
    supplier_name: str,
    supplier_trade_name: str | None,
    supplier_address: str | None,
    supplier_ubigeo: str | None,
    customer_doc_type: str,
    customer_doc_number: str,
    customer_name: str,
    customer_address: str | None,
    items: list[dict],
    total_gravada: Decimal,
    total_igv: Decimal,
    total_amount: Decimal,
) -> str:
    root = etree.Element("Invoice", nsmap=NAMESPACES)

    # UBL Extensions (placeholder for signature)
    ext_container = _el(root, EXT, "UBLExtensions")
    ext = _el(ext_container, EXT, "UBLExtension")
    _el(ext, EXT, "ExtensionContent")

    # UBL Version
    _el(root, CBC, "UBLVersionID", "2.1")
    _el(root, CBC, "CustomizationID", "2.0")

    # Document ID
    doc_id = f"{series}-{correlative}"
    _el(root, CBC, "ID", doc_id)
    _el(root, CBC, "IssueDate", issue_date)
    _el(
        root, CBC, "InvoiceTypeCode", document_type,
        listAgencyName="PE:SUNAT",
        listName="Tipo de Documento",
        listURI="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01",
        listID="0101",
        listSchemeURI="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo51",
        name="Tipo de Operacion",
    )
    _el(root, CBC, "DocumentCurrencyCode", currency)

    # Signature reference
    sig_ref = _el(root, CAC, "Signature")
    _el(sig_ref, CBC, "ID", f"SIG-{doc_id}")
    sig_party = _el(sig_ref, CAC, "SignatoryParty")
    sig_party_id = _el(sig_party, CAC, "PartyIdentification")
    _el(sig_party_id, CBC, "ID", supplier_ruc)
    sig_party_name = _el(sig_party, CAC, "PartyName")
    _el(sig_party_name, CBC, "Name", supplier_name)
    sig_attach = _el(sig_ref, CAC, "DigitalSignatureAttachment")
    sig_ext_ref = _el(sig_attach, CAC, "ExternalReference")
    _el(sig_ext_ref, CBC, "URI", f"#SIG-{doc_id}")

    # Supplier (AccountingSupplierParty)
    supplier = _el(root, CAC, "AccountingSupplierParty")
    supplier_party = _el(supplier, CAC, "Party")
    supplier_party_id = _el(supplier_party, CAC, "PartyIdentification")
    _el(supplier_party_id, CBC, "ID", supplier_ruc, schemeID="6")
    supplier_party_name = _el(supplier_party, CAC, "PartyName")
    _el(supplier_party_name, CBC, "Name", supplier_trade_name or supplier_name)
    supplier_legal = _el(supplier_party, CAC, "PartyLegalEntity")
    _el(supplier_legal, CBC, "RegistrationName", supplier_name)
    reg_addr = _el(supplier_legal, CAC, "RegistrationAddress")
    if supplier_ubigeo:
        _el(reg_addr, CBC, "ID", supplier_ubigeo)
    _el(reg_addr, CBC, "AddressTypeCode", "0000")
    if supplier_address:
        _el(reg_addr, CBC, "StreetName", supplier_address)
    country = _el(reg_addr, CAC, "Country")
    _el(country, CBC, "IdentificationCode", "PE")

    # Customer (AccountingCustomerParty)
    customer = _el(root, CAC, "AccountingCustomerParty")
    customer_party = _el(customer, CAC, "Party")
    customer_party_id = _el(customer_party, CAC, "PartyIdentification")
    _el(customer_party_id, CBC, "ID", customer_doc_number, schemeID=customer_doc_type)
    customer_legal = _el(customer_party, CAC, "PartyLegalEntity")
    _el(customer_legal, CBC, "RegistrationName", customer_name)
    if customer_address:
        cust_addr = _el(customer_legal, CAC, "RegistrationAddress")
        _el(cust_addr, CBC, "StreetName", customer_address)

    # Payment Terms (Contado)
    payment_terms = _el(root, CAC, "PaymentTerms")
    _el(payment_terms, CBC, "ID", "FormaPago")
    _el(payment_terms, CBC, "PaymentMeansID", "Contado")

    # Tax Total
    tax_total = _el(root, CAC, "TaxTotal")
    _amount(tax_total, CBC, "TaxAmount", total_igv, currency)

    # Group items by tax type for document-level TaxSubtotals
    tax_groups: dict[str, dict] = {}
    for item in items:
        igv_type = item.get("igv_type", "10")
        prefix = igv_type[0]
        if prefix not in tax_groups:
            tax_groups[prefix] = {"taxable": Decimal("0"), "tax": Decimal("0")}
        tax_groups[prefix]["taxable"] += item["line_extension"]
        tax_groups[prefix]["tax"] += item["igv"]

    for prefix, totals in tax_groups.items():
        scheme = TAX_SCHEMES.get(prefix, TAX_SCHEMES["1"])
        tax_subtotal = _el(tax_total, CAC, "TaxSubtotal")
        _amount(tax_subtotal, CBC, "TaxableAmount", totals["taxable"], currency)
        _amount(tax_subtotal, CBC, "TaxAmount", totals["tax"], currency)
        tax_cat = _el(tax_subtotal, CAC, "TaxCategory")
        tax_scheme = _el(tax_cat, CAC, "TaxScheme")
        _el(tax_scheme, CBC, "ID", scheme["id"])
        _el(tax_scheme, CBC, "Name", scheme["name"])
        _el(tax_scheme, CBC, "TaxTypeCode", scheme["code"])

    # Legal Monetary Total
    monetary = _el(root, CAC, "LegalMonetaryTotal")
    _amount(monetary, CBC, "LineExtensionAmount", total_gravada, currency)
    _amount(monetary, CBC, "TaxInclusiveAmount", total_amount, currency)
    _amount(monetary, CBC, "PayableAmount", total_amount, currency)

    # Invoice Lines
    for idx, item in enumerate(items, 1):
        igv_type = item.get("igv_type", "10")
        prefix = igv_type[0]
        scheme = TAX_SCHEMES.get(prefix, TAX_SCHEMES["1"])
        igv_percent = "18.00" if prefix == "1" else "0.00"

        line = _el(root, CAC, "InvoiceLine")
        _el(line, CBC, "ID", str(idx))
        _quantity(line, CBC, "InvoicedQuantity", item["quantity"], item.get("unit_code", "NIU"))
        _amount(line, CBC, "LineExtensionAmount", item["line_extension"], currency)

        # Pricing Reference (price with IGV for gravado, same price for exonerado/inafecto)
        pricing = _el(line, CAC, "PricingReference")
        alt_price = _el(pricing, CAC, "AlternativeConditionPrice")
        _price(alt_price, CBC, "PriceAmount", item["price_with_igv"], currency)
        _el(alt_price, CBC, "PriceTypeCode", "01")

        # Tax
        line_tax = _el(line, CAC, "TaxTotal")
        _amount(line_tax, CBC, "TaxAmount", item["igv"], currency)
        line_subtotal = _el(line_tax, CAC, "TaxSubtotal")
        _amount(line_subtotal, CBC, "TaxableAmount", item["line_extension"], currency)
        _amount(line_subtotal, CBC, "TaxAmount", item["igv"], currency)
        line_cat = _el(line_subtotal, CAC, "TaxCategory")
        _el(line_cat, CBC, "Percent", igv_percent)
        _el(line_cat, CBC, "TaxExemptionReasonCode", igv_type)
        line_scheme = _el(line_cat, CAC, "TaxScheme")
        _el(line_scheme, CBC, "ID", scheme["id"])
        _el(line_scheme, CBC, "Name", scheme["name"])
        _el(line_scheme, CBC, "TaxTypeCode", scheme["code"])

        # Item description
        inv_item = _el(line, CAC, "Item")
        _el(inv_item, CBC, "Description", item["description"])

        # Price (without tax, up to 10 decimals)
        price = _el(line, CAC, "Price")
        _price(price, CBC, "PriceAmount", item["unit_price"], currency)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode()
