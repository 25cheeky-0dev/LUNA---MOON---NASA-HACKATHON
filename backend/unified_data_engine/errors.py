class DatasetError(ValueError):
    """An explicit dataset or scientific-contract failure."""

    def __init__(self, code, detail, status=422):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status
