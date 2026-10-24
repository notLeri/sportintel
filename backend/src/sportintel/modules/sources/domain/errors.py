from sportintel.platform.errors import Conflict


class SourceDomainExists(Conflict):
    code = "source.domain_exists"
    title = "A source with this domain already exists"
