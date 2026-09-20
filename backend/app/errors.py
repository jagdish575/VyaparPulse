"""Domain errors. Messages are written to be shown to end users (never raw stack traces)."""


class KiraiError(Exception):
    status_code = 400
    code = "kirai_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(KiraiError):
    status_code = 404
    code = "not_found"


class ValidationFailedError(KiraiError):
    status_code = 422
    code = "invalid_request"


class InsufficientStockError(KiraiError):
    status_code = 409
    code = "insufficient_stock"

    def __init__(self, product_name: str, available: int, requested: int):
        self.product_name = product_name
        self.available = available
        self.requested = requested
        if available <= 0:
            msg = f"{product_name} is currently out of stock."
        else:
            msg = f"Only {available} {product_name} are currently available (requested {requested})."
        super().__init__(msg)
