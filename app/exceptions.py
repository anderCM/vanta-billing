class BillingError(Exception):
    pass


class MissingCredentialsError(BillingError):
    pass


class SUNATError(BillingError):
    pass


class XMLBuildError(BillingError):
    pass


class XMLSignError(BillingError):
    pass


class CDRParseError(BillingError):
    pass
