"""SOAP constants: namespaces, envelope templates, and SUNAT-specific values."""

# --- SOAP XML namespaces ---

NS_SOAPENV = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SERVICE = "http://service.sunat.gob.pe"
NS_WSSE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-wssecurity-secext-1.0.xsd"
)

# --- SOAP envelope templates ---

SEND_BILL_TEMPLATE = """\
<soapenv:Envelope xmlns:soapenv="{ns_soap}"
                  xmlns:ser="{ns_ser}"
                  xmlns:wsse="{ns_wsse}">
  <soapenv:Header>
    <wsse:Security>
      <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password>{password}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <ser:sendBill>
      <fileName>{filename}</fileName>
      <contentFile>{content}</contentFile>
    </ser:sendBill>
  </soapenv:Body>
</soapenv:Envelope>"""

GET_STATUS_TEMPLATE = """\
<soapenv:Envelope xmlns:soapenv="{ns_soap}"
                  xmlns:ser="{ns_ser}"
                  xmlns:wsse="{ns_wsse}">
  <soapenv:Header>
    <wsse:Security>
      <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password>{password}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <ser:getStatusCdr>
      <rucComprobante>{ruc}</rucComprobante>
      <tipoComprobante>{doc_type}</tipoComprobante>
      <serieComprobante>{series}</serieComprobante>
      <numeroComprobante>{correlative}</numeroComprobante>
    </ser:getStatusCdr>
  </soapenv:Body>
</soapenv:Envelope>"""

# --- SOAP action headers ---

SOAP_ACTION_SEND_BILL = "urn:sendBill"
SOAP_ACTION_GET_STATUS_CDR = "urn:getStatusCdr"
