class AppError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = 'request-failed'):
        super().__init__(message)
        self.status = status
        self.code = code
