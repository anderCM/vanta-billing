"""Builds UBL 2.1 DespatchAdvice XML for Guías de Remisión."""

from lxml import etree

NAMESPACES_GR = {
    None: "urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
}

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"


def _el(parent, ns, tag, text=None, **attribs):
    el = etree.SubElement(parent, f"{{{ns}}}{tag}" if ns else tag, **attribs)
    if text is not None:
        el.text = str(text)
    return el


def build_despatch_advice_xml(
    *,
    document_type: str,
    series: str,
    correlative: int,
    issue_date: str,
    issue_time: str,
    # Issuer (supplier)
    supplier_ruc: str,
    supplier_name: str,
    supplier_address: str | None,
    supplier_ubigeo: str | None,
    # Recipient
    recipient_doc_type: str,
    recipient_doc_number: str,
    recipient_name: str,
    # Shipment
    transfer_reason: str,
    transport_modality: str,
    transfer_date: str,
    gross_weight: str,
    weight_unit_code: str,
    departure_address: str,
    departure_ubigeo: str,
    arrival_address: str,
    arrival_ubigeo: str,
    # Carrier / vehicle / driver
    carrier_ruc: str | None,
    carrier_name: str | None,
    vehicle_plate: str | None,
    driver_doc_type: str | None,
    driver_doc_number: str | None,
    driver_name: str | None,
    driver_license: str | None,
    # GRT-specific shipper
    shipper_doc_type: str | None,
    shipper_doc_number: str | None,
    shipper_name: str | None,
    # Related document reference (optional)
    related_document_type: str | None = None,
    related_document_number: str | None = None,
    # Items
    items: list[dict],
) -> str:
    root = etree.Element("DespatchAdvice", nsmap=NAMESPACES_GR)

    # UBL Extensions (placeholder for signature)
    ext_container = _el(root, EXT, "UBLExtensions")
    ext = _el(ext_container, EXT, "UBLExtension")
    _el(ext, EXT, "ExtensionContent")

    _el(root, CBC, "UBLVersionID", "2.1")
    _el(root, CBC, "CustomizationID", "2.0")

    doc_id = f"{series}-{correlative:08d}"
    _el(root, CBC, "ID", doc_id)
    _el(root, CBC, "IssueDate", issue_date)
    _el(root, CBC, "IssueTime", issue_time)
    _el(
        root,
        CBC,
        "DespatchAdviceTypeCode",
        document_type,
        listAgencyName="PE:SUNAT",
        listName="Tipo de Documento",
        listURI="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01",
    )

    # Signature reference block
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

    # AdditionalDocumentReference (optional: related invoice/receipt)
    if related_document_type and related_document_number:
        add_doc_ref = _el(root, CAC, "AdditionalDocumentReference")
        _el(add_doc_ref, CBC, "ID", related_document_number)
        _el(
            add_doc_ref,
            CBC,
            "DocumentTypeCode",
            related_document_type,
            listAgencyName="PE:SUNAT",
            listName="Tipo de Documento",
            listURI="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01",
        )

    # DespatchSupplierParty (issuer)
    supplier = _el(root, CAC, "DespatchSupplierParty")
    supplier_party = _el(supplier, CAC, "Party")
    supplier_party_id = _el(supplier_party, CAC, "PartyIdentification")
    _el(supplier_party_id, CBC, "ID", supplier_ruc, schemeID="6")
    supplier_legal = _el(supplier_party, CAC, "PartyLegalEntity")
    _el(supplier_legal, CBC, "RegistrationName", supplier_name)
    reg_addr = _el(supplier_legal, CAC, "RegistrationAddress")
    if supplier_ubigeo:
        _el(reg_addr, CBC, "ID", supplier_ubigeo)
    _el(reg_addr, CBC, "AddressTypeCode", "0000")
    if supplier_address:
        supplier_addr_line = _el(reg_addr, CAC, "AddressLine")
        _el(supplier_addr_line, CBC, "Line", supplier_address)

    # DeliveryCustomerParty (recipient)
    customer = _el(root, CAC, "DeliveryCustomerParty")
    customer_party = _el(customer, CAC, "Party")
    customer_party_id = _el(customer_party, CAC, "PartyIdentification")
    _el(
        customer_party_id,
        CBC,
        "ID",
        recipient_doc_number,
        schemeID=recipient_doc_type,
    )
    customer_legal = _el(customer_party, CAC, "PartyLegalEntity")
    _el(customer_legal, CBC, "RegistrationName", recipient_name)

    # GRT: SellerSupplierParty (the original shipper/sender)
    if document_type == "31" and shipper_doc_number:
        shipper = _el(root, CAC, "SellerSupplierParty")
        shipper_party = _el(shipper, CAC, "Party")
        shipper_party_id = _el(shipper_party, CAC, "PartyIdentification")
        _el(
            shipper_party_id,
            CBC,
            "ID",
            shipper_doc_number,
            schemeID=shipper_doc_type or "6",
        )
        shipper_legal = _el(shipper_party, CAC, "PartyLegalEntity")
        _el(shipper_legal, CBC, "RegistrationName", shipper_name)

    # Shipment block
    shipment = _el(root, CAC, "Shipment")
    _el(shipment, CBC, "ID", "SUNAT_Envio")
    _el(shipment, CBC, "HandlingCode", transfer_reason)
    _el(
        shipment,
        CBC,
        "GrossWeightMeasure",
        gross_weight,
        unitCode=weight_unit_code,
    )

    # ShipmentStage: transport modality
    stage = _el(shipment, CAC, "ShipmentStage")
    _el(stage, CBC, "TransportModeCode", transport_modality)
    period = _el(stage, CAC, "TransitPeriod")
    _el(period, CBC, "StartDate", transfer_date)

    # Carrier party (GRR public transport)
    if document_type == "09" and transport_modality == "01" and carrier_ruc:
        carrier_party_el = _el(stage, CAC, "CarrierParty")
        c_party_id = _el(carrier_party_el, CAC, "PartyIdentification")
        _el(c_party_id, CBC, "ID", carrier_ruc, schemeID="6")
        c_legal = _el(carrier_party_el, CAC, "PartyLegalEntity")
        _el(c_legal, CBC, "RegistrationName", carrier_name)

    # Driver info in ShipmentStage
    if driver_doc_number and driver_name:
        driver_person = _el(stage, CAC, "DriverPerson")
        _el(driver_person, CBC, "ID", driver_doc_number, schemeID=driver_doc_type or "1")
        _el(driver_person, CBC, "FirstName", driver_name)
        if driver_license:
            _el(driver_person, CBC, "JobTitle", driver_license)

    # Delivery: departure and arrival addresses
    delivery = _el(shipment, CAC, "Delivery")
    delivery_addr = _el(delivery, CAC, "DeliveryAddress")
    _el(delivery_addr, CBC, "ID", arrival_ubigeo)
    arrival_line = _el(delivery_addr, CAC, "AddressLine")
    _el(arrival_line, CBC, "Line", arrival_address)

    despatch = _el(delivery, CAC, "Despatch")
    despatch_addr = _el(despatch, CAC, "DespatchAddress")
    _el(despatch_addr, CBC, "ID", departure_ubigeo)
    departure_line = _el(despatch_addr, CAC, "AddressLine")
    _el(departure_line, CBC, "Line", departure_address)

    # TransportHandlingUnit: vehicle plate
    if vehicle_plate:
        thu = _el(shipment, CAC, "TransportHandlingUnit")
        _el(thu, CBC, "ID", vehicle_plate)
        transport_equip = _el(thu, CAC, "TransportEquipment")
        _el(transport_equip, CBC, "ID", vehicle_plate)

    # DespatchLine per item
    for idx, item in enumerate(items, 1):
        line = _el(root, CAC, "DespatchLine")
        _el(line, CBC, "ID", str(idx))
        qty = etree.SubElement(
            line,
            f"{{{CBC}}}DeliveredQuantity",
            unitCode=item.get("unit_code", "NIU"),
        )
        qty.text = str(item["quantity"])
        order_ref = _el(line, CAC, "OrderLineReference")
        _el(order_ref, CBC, "LineID", str(idx))
        line_item = _el(line, CAC, "Item")
        _el(line_item, CBC, "Description", item["description"])

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode()
